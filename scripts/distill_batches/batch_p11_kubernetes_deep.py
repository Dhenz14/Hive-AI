PAIRS = [
    # --- 1. Custom Resource Definitions and Operators ---
    (
        "kubernetes/custom-resource-definitions-operators",
        r"""Explain how to design Kubernetes Custom Resource Definitions and build production-grade operators using controller-runtime, including the reconciliation loop pattern, status subresource management, finalizers for cleanup, and leader election for high availability""",
        r"""# Custom Resource Definitions and Kubernetes Operators: Production-Grade Patterns

## Understanding CRDs and the Operator Pattern

A **Custom Resource Definition** (CRD) extends the Kubernetes API by introducing domain-specific objects that behave like built-in resources (Pods, Services, Deployments). An **Operator** pairs a CRD with a custom controller that watches these resources and drives the cluster toward the desired state. This is powerful **because** it encodes complex operational knowledge -- deployment strategies, failover procedures, backup schedules -- into declarative, auditable, version-controlled software rather than runbooks or manual steps.

The **trade-off** is complexity: building a correct, resilient operator requires understanding eventual consistency, idempotent reconciliation, finalizer semantics, and leader election. A **common mistake** is treating the reconciliation loop like an imperative script rather than a convergence engine.

## Designing a CRD with Structural Schema

**Best practice**: always define a structural OpenAPI v3 schema with validation constraints. Without it, Kubernetes accepts any JSON, making debugging painful.

```yaml
# crd-messagequeue.yaml
# Defines a MessageQueue custom resource with validation
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: messagequeues.messaging.example.io
  annotations:
    controller-gen.kubebuilder.io/version: v0.14.0
spec:
  group: messaging.example.io
  names:
    kind: MessageQueue
    listKind: MessageQueueList
    plural: messagequeues
    singular: messagequeue
    shortNames:
      - mq
  scope: Namespaced
  versions:
    - name: v1alpha1
      served: true
      storage: true
      subresources:
        status: {}       # Enable status subresource for split permissions
        scale:
          specReplicasPath: .spec.replicas
          statusReplicasPath: .status.readyReplicas
      additionalPrinterColumns:
        - name: Replicas
          type: integer
          jsonPath: .spec.replicas
        - name: Ready
          type: integer
          jsonPath: .status.readyReplicas
        - name: Phase
          type: string
          jsonPath: .status.phase
        - name: Age
          type: date
          jsonPath: .metadata.creationTimestamp
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: ["replicas", "storageSize"]
              properties:
                replicas:
                  type: integer
                  minimum: 1
                  maximum: 9
                  description: "Number of broker instances"
                storageSize:
                  type: string
                  pattern: "^[0-9]+(Gi|Ti)$"
                retentionDays:
                  type: integer
                  default: 7
                  minimum: 1
                  maximum: 90
                tlsEnabled:
                  type: boolean
                  default: true
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: ["Pending", "Provisioning", "Running", "Degraded", "Failed"]
                readyReplicas:
                  type: integer
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                      status:
                        type: string
                      lastTransitionTime:
                        type: string
                        format: date-time
                      reason:
                        type: string
                      message:
                        type: string
```

The **status subresource** is critical **because** it separates spec writes (user intent) from status writes (controller observations). This means RBAC can grant users permission to update `.spec` while restricting `.status` updates to the controller only. **Therefore**, controllers must use the status client: `r.Status().Update(ctx, &mq)`.

## Building the Operator with controller-runtime

```go
// controllers/messagequeue_controller.go
package controllers

import (
	"context"
	"fmt"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	messagingv1alpha1 "example.io/mq-operator/api/v1alpha1"
)

const mqFinalizer = "messaging.example.io/cleanup"

// MessageQueueReconciler reconciles a MessageQueue object
type MessageQueueReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=messaging.example.io,resources=messagequeues,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=messaging.example.io,resources=messagequeues/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=messaging.example.io,resources=messagequeues/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=statefulsets,verbs=get;list;watch;create;update;patch;delete

func (r *MessageQueueReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Step 1: Fetch the custom resource
	var mq messagingv1alpha1.MessageQueue
	if err := r.Get(ctx, req.NamespacedName, &mq); err != nil {
		if errors.IsNotFound(err) {
			// Resource deleted before reconcile -- nothing to do
			logger.Info("MessageQueue not found, likely deleted")
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// Step 2: Handle finalizer for cleanup logic
	// Finalizers prevent deletion until external resources are cleaned up
	if mq.ObjectMeta.DeletionTimestamp.IsZero() {
		// Resource is NOT being deleted -- ensure finalizer is present
		if !controllerutil.ContainsFinalizer(&mq, mqFinalizer) {
			controllerutil.AddFinalizer(&mq, mqFinalizer)
			if err := r.Update(ctx, &mq); err != nil {
				return ctrl.Result{}, err
			}
		}
	} else {
		// Resource IS being deleted -- run cleanup
		if controllerutil.ContainsFinalizer(&mq, mqFinalizer) {
			if err := r.cleanupExternalResources(ctx, &mq); err != nil {
				return ctrl.Result{}, err
			}
			controllerutil.RemoveFinalizer(&mq, mqFinalizer)
			if err := r.Update(ctx, &mq); err != nil {
				return ctrl.Result{}, err
			}
		}
		return ctrl.Result{}, nil
	}

	// Step 3: Reconcile the StatefulSet
	desired := r.desiredStatefulSet(&mq)
	// SetControllerReference ensures garbage collection on CR deletion
	if err := controllerutil.SetControllerReference(&mq, desired, r.Scheme); err != nil {
		return ctrl.Result{}, err
	}

	var existing appsv1.StatefulSet
	err := r.Get(ctx, types.NamespacedName{Name: desired.Name, Namespace: desired.Namespace}, &existing)
	if errors.IsNotFound(err) {
		logger.Info("Creating StatefulSet", "name", desired.Name)
		if err := r.Create(ctx, desired); err != nil {
			return ctrl.Result{}, err
		}
	} else if err != nil {
		return ctrl.Result{}, err
	} else {
		// Update if spec diverged
		existing.Spec.Replicas = desired.Spec.Replicas
		existing.Spec.Template = desired.Spec.Template
		if err := r.Update(ctx, &existing); err != nil {
			return ctrl.Result{}, err
		}
	}

	// Step 4: Update status subresource
	mq.Status.Phase = "Running"
	mq.Status.ReadyReplicas = existing.Status.ReadyReplicas
	if err := r.Status().Update(ctx, &mq); err != nil {
		logger.Error(err, "Failed to update status")
		return ctrl.Result{}, err
	}

	// Requeue after 30s for periodic health checks
	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

func (r *MessageQueueReconciler) cleanupExternalResources(ctx context.Context, mq *messagingv1alpha1.MessageQueue) error {
	// Pitfall: if cleanup fails, the finalizer blocks deletion forever
	// Best practice: implement timeout and fallback logic
	logger := log.FromContext(ctx)
	logger.Info("Cleaning up external resources", "queue", mq.Name)
	// e.g., drain messages, deregister from service discovery, delete PVs
	return nil
}

func (r *MessageQueueReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&messagingv1alpha1.MessageQueue{}).
		Owns(&appsv1.StatefulSet{}).  // Watch owned StatefulSets
		Complete(r)
}
```

### Leader Election for High Availability

When running multiple operator replicas, **leader election** ensures only one instance actively reconciles. The **trade-off** is availability vs. split-brain risk.

```go
// main.go -- enabling leader election
func main() {
	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 scheme,
		LeaderElection:         true,
		LeaderElectionID:       "mq-operator-leader.messaging.example.io",
		// Best practice: use a dedicated namespace for the leader lock
		LeaderElectionNamespace: "mq-operator-system",
		// Pitfall: too-short lease duration causes flapping
		LeaseDuration: durationPtr(30 * time.Second),
		RenewDeadline: durationPtr(20 * time.Second),
		RetryPeriod:   durationPtr(5 * time.Second),
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}
}

func durationPtr(d time.Duration) *time.Duration {
	return &d
}
```

## Key Reconciliation Loop Principles

1. **Idempotency**: calling Reconcile 100 times with the same input must produce the same result
2. **Level-triggered, not edge-triggered**: react to current state, not change events
3. **Requeue on transient errors**: return `ctrl.Result{RequeueAfter: ...}` for retryable failures
4. **Observe, diff, act**: always read the current state before making changes

A **common mistake** is performing destructive actions (deleting a Pod, scaling down) without first confirming the current state. The reconcile function should always `Get` the resource, compare desired vs. actual, and only then act. **Therefore**, treat every reconciliation as if it could be called at any time for any reason -- **because** it will be.

### Common Pitfalls

- **Forgetting the status subresource**: writing status fields on the main resource silently drops them when the status subresource is enabled. You must use `r.Status().Update()` instead of `r.Update()` for status changes
- **Infinite reconcile loops**: updating the resource in Reconcile triggers another Reconcile -- use `Update` on status subresource separately, and check whether a change is actually needed before writing
- **Not setting OwnerReferences**: orphaned child resources after CR deletion. Always use `controllerutil.SetControllerReference` to establish the ownership chain
- **Blocking in Reconcile**: long-running operations (provisioning cloud resources, waiting for DNS propagation) should be async with status polling. Set the status to `Provisioning` and requeue with a delay
- **Not handling resource version conflicts**: concurrent updates cause `409 Conflict` errors. **Best practice**: always re-fetch the resource after a conflict and retry the reconciliation

## Testing Operators

Testing is essential for operator reliability. Use **envtest** from controller-runtime to spin up a real API server and etcd without a full cluster:

```go
// controllers/messagequeue_controller_test.go
package controllers

import (
	"context"
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"

	messagingv1alpha1 "example.io/mq-operator/api/v1alpha1"
)

var _ = Describe("MessageQueue Controller", func() {
	const timeout = time.Second * 30
	const interval = time.Second * 1

	Context("When creating a MessageQueue", func() {
		It("Should create a StatefulSet with correct replicas", func() {
			ctx := context.Background()
			mq := &messagingv1alpha1.MessageQueue{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-mq",
					Namespace: "default",
				},
				Spec: messagingv1alpha1.MessageQueueSpec{
					Replicas:    3,
					StorageSize: "10Gi",
				},
			}
			Expect(k8sClient.Create(ctx, mq)).Should(Succeed())

			// Verify the controller creates the StatefulSet
			Eventually(func() int32 {
				var created messagingv1alpha1.MessageQueue
				err := k8sClient.Get(ctx, types.NamespacedName{
					Name: "test-mq", Namespace: "default",
				}, &created)
				if err != nil {
					return 0
				}
				return created.Status.ReadyReplicas
			}, timeout, interval).Should(Equal(int32(3)))
		})
	})
})
```

**Best practice**: write integration tests with envtest for the happy path and unit tests for edge cases (conflict handling, finalizer cleanup, error scenarios). **However**, envtest does not simulate node-level behavior, so end-to-end tests in a Kind or k3d cluster are still necessary for full validation.

## Summary / Key Takeaways

- **CRDs** extend the Kubernetes API; always define structural schemas with validation constraints and printer columns for better kubectl output
- **controller-runtime** provides the scaffolding for building robust operators in Go, including caching, event filtering, and leader election
- The **reconciliation loop** must be idempotent and level-triggered, converging toward desired state on every invocation
- **Finalizers** enable cleanup of external resources before CR deletion, but a **pitfall** is that failed cleanup blocks deletion indefinitely -- implement timeout and fallback logic
- **Status subresource** separates user intent from controller observations and enables fine-grained RBAC; **therefore** always enable it on production CRDs
- **Leader election** prevents split-brain in multi-replica operator deployments; **therefore** always enable it in production with appropriate lease duration tuning
- **Best practice**: use `controllerutil.SetControllerReference` for automatic garbage collection of child resources, and test with envtest for reliable operator behavior
""",
    ),

    # --- 2. Admission Webhooks ---
    (
        "kubernetes/admission-webhooks-policy-engines",
        r"""Describe Kubernetes admission webhooks including validating and mutating webhook configurations, integration with OPA Gatekeeper and Kyverno policy engines, webhook failure mode strategies, TLS certificate management, and debugging common webhook issues in production clusters""",
        r"""# Kubernetes Admission Webhooks: Validating, Mutating, and Policy Engines

## How Admission Webhooks Work

When a request hits the Kubernetes API server (e.g., `kubectl apply -f pod.yaml`), it passes through a chain: **authentication -> authorization -> mutating admission -> object schema validation -> validating admission -> persistence to etcd**. Admission webhooks intercept requests at the mutating and validating stages, enabling you to inject sidecars, enforce policies, set defaults, and reject non-compliant resources.

This is powerful **because** it provides a centralized, declarative enforcement point. **However**, the **trade-off** is that a misconfigured or unavailable webhook can block all cluster operations -- including critical system components.

### Mutating vs. Validating Webhooks

- **Mutating webhooks** modify the incoming object (inject labels, add sidecars, set defaults). They run first so validating webhooks see the final form.
- **Validating webhooks** accept or reject without modification. They run second and can enforce invariants.

A **common mistake** is using a validating webhook to check something that a mutating webhook could fix automatically. **Best practice**: mutate to fix, validate to reject.

## Webhook Configuration

```yaml
# mutating-webhook-config.yaml
# Injects resource limits on all new pods that lack them
apiVersion: admissionregistration.k8s.io/v1
kind: MutatingWebhookConfiguration
metadata:
  name: resource-defaults-injector
  labels:
    app: policy-engine
webhooks:
  - name: resource-defaults.example.io
    admissionReviewVersions: ["v1"]
    sideEffects: None
    # Best practice: use namespaceSelector to skip kube-system
    namespaceSelector:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values: ["kube-system", "kube-public", "cert-manager"]
    rules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE"]
        resources: ["pods"]
        scope: Namespaced
    clientConfig:
      # Option A: In-cluster service
      service:
        name: webhook-server
        namespace: policy-system
        path: /mutate-pod-defaults
        port: 443
      # The CA bundle that signed the webhook server's TLS cert
      caBundle: LS0tLS1CRUdJTi...base64-encoded-CA...
    # CRITICAL: failure policy determines behavior when webhook is down
    failurePolicy: Ignore   # Fail-open: allow request if webhook unreachable
    # Pitfall: setting Fail (fail-closed) can lock out the entire cluster
    matchPolicy: Equivalent
    timeoutSeconds: 5       # Short timeout to avoid blocking API server
    reinvocationPolicy: IfNeeded
```

```yaml
# validating-webhook-config.yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: security-policy-validator
webhooks:
  - name: security-policy.example.io
    admissionReviewVersions: ["v1"]
    sideEffects: None
    failurePolicy: Fail     # Fail-closed for security policies
    namespaceSelector:
      matchExpressions:
        - key: policy.example.io/enforce
          operator: In
          values: ["true"]
    rules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["deployments"]
    clientConfig:
      service:
        name: security-validator
        namespace: policy-system
        path: /validate-deployment-security
        port: 443
      caBundle: LS0tLS1CRUdJTi...
    timeoutSeconds: 10
```

## Implementing a Webhook Server in Go

```go
// cmd/webhook/main.go
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	admissionv1 "k8s.io/api/admission/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// handleMutatePods injects default resource limits
func handleMutatePods(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "read body failed", http.StatusBadRequest)
		return
	}

	var review admissionv1.AdmissionReview
	if err := json.Unmarshal(body, &review); err != nil {
		http.Error(w, "unmarshal failed", http.StatusBadRequest)
		return
	}

	var pod corev1.Pod
	if err := json.Unmarshal(review.Request.Object.Raw, &pod); err != nil {
		sendResponse(w, review, false, "cannot parse pod", nil)
		return
	}

	// Build JSON patches for containers missing resource limits
	var patches []map[string]interface{}
	for i, container := range pod.Spec.Containers {
		if container.Resources.Limits == nil {
			patches = append(patches, map[string]interface{}{
				"op":   "add",
				"path": fmt.Sprintf("/spec/containers/%d/resources/limits", i),
				"value": corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("500m"),
					corev1.ResourceMemory: resource.MustParse("256Mi"),
				},
			})
		}
	}

	patchBytes, _ := json.Marshal(patches)
	patchType := admissionv1.PatchTypeJSONPatch
	sendResponse(w, review, true, "", &admissionv1.AdmissionResponse{
		Allowed:   true,
		PatchType: &patchType,
		Patch:     patchBytes,
	})
}

func sendResponse(w http.ResponseWriter, review admissionv1.AdmissionReview, allowed bool, msg string, resp *admissionv1.AdmissionResponse) {
	if resp == nil {
		resp = &admissionv1.AdmissionResponse{
			Allowed: allowed,
			Result:  &metav1.Status{Message: msg},
		}
	}
	resp.UID = review.Request.UID
	review.Response = resp
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(review)
}

func main() {
	http.HandleFunc("/mutate-pod-defaults", handleMutatePods)
	// TLS is mandatory -- API server only speaks HTTPS to webhooks
	http.ListenAndServeTLS(":8443", "/certs/tls.crt", "/certs/tls.key", nil)
}
```

## OPA Gatekeeper vs. Kyverno

**OPA Gatekeeper** uses the Rego policy language. It is extremely expressive but has a steep learning curve. **Kyverno** uses YAML-native policies, making it more approachable for teams that don't want to learn Rego. **Therefore**, choose Gatekeeper for complex cross-resource policies and Kyverno for straightforward admission rules.

### OPA Gatekeeper Example

Gatekeeper separates policy templates (the Rego logic) from constraints (the parameters). This is powerful **because** one template can enforce many different constraints with different parameters.

```yaml
# OPA Gatekeeper ConstraintTemplate
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredlabels
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredLabels
      validation:
        openAPIV3Schema:
          type: object
          properties:
            labels:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredlabels
        # Rego policy: check all required labels are present
        violation[{"msg": msg}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.labels[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", [missing])
        }

---
# Constraint using the template
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: require-team-labels
spec:
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment"]
  parameters:
    labels: ["team", "environment", "cost-center"]
```

### Kyverno Example

```yaml
# Kyverno policy -- no-latest-tag.yaml
# Kyverno is a YAML-native alternative to OPA Gatekeeper
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: disallow-latest-tag
  annotations:
    policies.kyverno.io/title: Disallow Latest Tag
    policies.kyverno.io/severity: medium
spec:
  validationFailureAction: Enforce  # or Audit for dry-run
  background: true
  rules:
    - name: validate-image-tag
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "Using ':latest' tag is not allowed. Specify an explicit version tag."
        pattern:
          spec:
            containers:
              - image: "!*:latest"
    - name: require-resource-limits
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "All containers must have CPU and memory limits."
        pattern:
          spec:
            containers:
              - resources:
                  limits:
                    memory: "?*"
                    cpu: "?*"
```

## TLS Certificate Management for Webhooks

The API server requires HTTPS when calling webhooks. **Best practice**: use cert-manager to auto-rotate certificates.

```yaml
# cert-manager certificate for the webhook
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: webhook-server-cert
  namespace: policy-system
spec:
  secretName: webhook-server-tls
  dnsNames:
    - webhook-server.policy-system.svc
    - webhook-server.policy-system.svc.cluster.local
  issuerRef:
    name: selfsigned-issuer
    kind: ClusterIssuer
  duration: 8760h    # 1 year
  renewBefore: 720h  # Renew 30 days before expiry
```

### Failure Mode Strategies

| `failurePolicy` | Behavior | Use Case |
|---|---|---|
| `Fail` | Reject request if webhook is down | Security-critical policies |
| `Ignore` | Allow request if webhook is down | Non-critical mutations, defaults |

**Pitfall**: `Fail` on a webhook that matches `kube-system` resources can prevent the cluster from self-healing. **Best practice**: always exclude `kube-system` with `namespaceSelector` and set `timeoutSeconds` to 5 or less.

## Debugging Webhook Issues

When webhooks misbehave, diagnosis requires checking multiple layers. Here is a systematic approach:

- **Check webhook configurations**: `kubectl get mutatingwebhookconfigurations,validatingwebhookconfigurations` -- verify the webhook exists and its rules match the expected resources
- **API server logs**: look for `webhook` entries with `--v=5` to see exactly which webhooks are being called and what responses they return
- **Test with dry-run**: `kubectl apply -f pod.yaml --dry-run=server` triggers webhooks without persisting the object, making it safe to test in production
- **Common mistake**: the `caBundle` doesn't match the cert the webhook server presents, causing TLS handshake failures. Verify with: `kubectl get mutatingwebhookconfiguration <name> -o jsonpath='{.webhooks[0].clientConfig.caBundle}' | base64 -d | openssl x509 -noout -subject -issuer`
- **Network connectivity**: ensure the API server can reach the webhook service. A **pitfall** in private clusters is that firewall rules block the API server from reaching webhook pods on their serving port
- **Webhook latency**: if `timeoutSeconds` is too low and the webhook is slow, requests will fail intermittently. Monitor p99 latency and set the timeout accordingly. **Best practice**: keep webhook logic simple and fast -- under 100ms per request

### Emergency Recovery

If a webhook with `failurePolicy: Fail` is broken and blocking all operations, you can delete the webhook configuration directly through the API:

```bash
# Emergency: delete a broken webhook that is blocking cluster operations
# This bypasses the broken webhook because webhook configs themselves
# are not subject to admission webhooks
kubectl delete mutatingwebhookconfiguration resource-defaults-injector

# Pitfall: this removes ALL policy enforcement until the webhook is restored
# Therefore, fix the root cause and re-apply the webhook configuration promptly

# To temporarily disable without deleting, patch the failurePolicy
kubectl patch mutatingwebhookconfiguration resource-defaults-injector \
  --type='json' \
  -p='[{"op": "replace", "path": "/webhooks/0/failurePolicy", "value": "Ignore"}]'
```

## Summary / Key Takeaways

- **Mutating webhooks** modify requests (inject defaults, sidecars); **validating webhooks** accept or reject -- they form the policy enforcement layer of Kubernetes
- **Failure policy** is the most critical setting: `Fail` for security-critical policies, `Ignore` for non-critical enrichment. Getting this wrong can lock out the entire cluster
- **OPA Gatekeeper** excels at complex Rego-based cross-resource policies; **Kyverno** offers YAML-native simplicity -- the **trade-off** is expressiveness vs. accessibility
- Always use **cert-manager** for TLS certificate lifecycle; manual cert rotation is a **pitfall** that causes silent outages when certificates expire
- **Best practice**: exclude `kube-system` from webhook selectors, keep timeouts under 5 seconds, and monitor webhook latency with Prometheus metrics
- **Therefore**, treat admission webhooks as critical infrastructure: monitor them, alert on failures, and test thoroughly in staging before production enforcement
""",
    ),

    # --- 3. Kubernetes Networking Deep Dive ---
    (
        "kubernetes/networking-cni-service-mesh-gateway-api",
        r"""Provide a deep dive into Kubernetes networking covering CNI plugin architecture, Service types including ClusterIP LoadBalancer and NodePort, NetworkPolicy enforcement, CoreDNS configuration, Ingress controllers comparison, and the new Gateway API with practical YAML configurations and troubleshooting""",
        r"""# Kubernetes Networking Deep Dive: From CNI to Gateway API

## The Kubernetes Networking Model

Kubernetes enforces three fundamental networking rules: (1) every Pod gets a unique IP, (2) Pods can communicate with all other Pods without NAT, and (3) agents on a node can communicate with all Pods on that node. This flat networking model is powerful **because** it eliminates the need for port mapping and simplifies service discovery. **However**, the **trade-off** is that implementing this requires a CNI plugin that handles the actual packet routing.

## CNI Plugin Architecture

The **Container Network Interface** (CNI) is a specification for configuring network interfaces in Linux containers. When the kubelet creates a Pod, it calls the CNI plugin binary, which allocates an IP, creates a veth pair, and configures routes.

### Major CNI Plugins Compared

| Plugin | Overlay | Encryption | NetworkPolicy | Performance |
|--------|---------|-----------|---------------|------------|
| **Calico** | Optional (VXLAN/IPIP) | WireGuard | Full | High (eBPF mode) |
| **Cilium** | Optional (VXLAN/Geneve) | WireGuard/IPsec | Full + L7 | Highest (eBPF) |
| **Flannel** | VXLAN | No native | No | Moderate |
| **Weave** | VXLAN | IPsec | Partial | Moderate |

**Best practice**: use **Cilium** for new clusters **because** its eBPF dataplane bypasses iptables entirely, providing 3-10x better throughput for service routing. **However**, Calico remains excellent for hybrid environments needing BGP peering.

```yaml
# Cilium Helm values for production deployment
# helm install cilium cilium/cilium --namespace kube-system -f values.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cilium-config
  namespace: kube-system
data:
  # Enable eBPF-based kube-proxy replacement
  kube-proxy-replacement: "strict"
  # Enable WireGuard encryption between nodes
  enable-wireguard: "true"
  # Enable Hubble observability
  enable-hubble: "true"
  hubble-relay-enabled: "true"
  hubble-ui-enabled: "true"
  # IPAM mode -- cluster-pool for large clusters
  ipam: "cluster-pool"
  cluster-pool-ipv4-cidr: "10.0.0.0/8"
  cluster-pool-ipv4-mask-size: "24"
  # Enable bandwidth manager for fair queuing
  enable-bandwidth-manager: "true"
```

## Service Types and How They Work

### ClusterIP (Default)

Every Service gets a virtual IP from the service CIDR. kube-proxy (or eBPF) programs iptables/IPVS rules to DNAT traffic destined for the ClusterIP to a healthy Pod backend.

```yaml
# Standard ClusterIP service
apiVersion: v1
kind: Service
metadata:
  name: api-server
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: api-server
    version: v2
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
    - name: grpc
      port: 9090
      targetPort: 9090
      protocol: TCP
  # Best practice: set session affinity for stateful protocols
  sessionAffinity: ClientIP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 3600
```

### NodePort and LoadBalancer

**NodePort** opens a static port (30000-32767) on every node. **LoadBalancer** extends NodePort by provisioning a cloud load balancer. A **common mistake** is exposing NodePort services directly to the internet -- **therefore**, always use LoadBalancer or Ingress instead.

### Headless Services

Setting `clusterIP: None` creates a **headless service** that returns Pod IPs directly in DNS, essential for StatefulSets where clients need to connect to specific pods.

```yaml
# Headless service for a StatefulSet
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
spec:
  clusterIP: None
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
  # Pods are addressable as: postgres-0.postgres-headless.default.svc.cluster.local
```

## NetworkPolicy Enforcement

NetworkPolicies are Kubernetes-native firewalls. By default, all Pods accept all traffic. Once you apply a NetworkPolicy selecting a Pod, all non-matching traffic is **denied** (default-deny for the selected direction).

```yaml
# Default deny all ingress in a namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: production
spec:
  podSelector: {}    # Selects ALL pods in namespace
  policyTypes:
    - Ingress        # Deny all incoming by default

---
# Allow specific traffic: frontend -> api -> database
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-database
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: database
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-server
        # Pitfall: multiple items in 'from' are OR'd
        # Multiple selectors in ONE item are AND'd
        - namespaceSelector:
            matchLabels:
              environment: production
      ports:
        - protocol: TCP
          port: 5432
```

**Pitfall**: Flannel does **not** enforce NetworkPolicies. Calico, Cilium, and Weave Net do. A **common mistake** is applying NetworkPolicy manifests with Flannel and assuming they work -- they are silently ignored.

## CoreDNS Configuration

CoreDNS is the cluster DNS server. Every Pod gets a DNS search path: `<namespace>.svc.cluster.local -> svc.cluster.local -> cluster.local`.

```yaml
# CoreDNS Corefile ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health {
            lameduck 5s
        }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
            pods insecure
            fallthrough in-addr.arpa ip6.arpa
            ttl 30
        }
        # Forward external DNS to upstream
        forward . /etc/resolv.conf {
            max_concurrent 1000
        }
        # Custom domain forwarding
        # Best practice: forward internal domains to corporate DNS
        # Trade-off: adds latency for those lookups
        forward corp.example.com 10.0.0.53 10.0.0.54 {
            force_tcp
        }
        cache 30
        loop
        reload
        loadbalance
    }
```

## Ingress Controllers vs. Gateway API

**Ingress** is the legacy L7 routing API. **Gateway API** is the successor, offering richer routing, multi-tenancy, and role-oriented design.

```yaml
# Gateway API -- GatewayClass, Gateway, and HTTPRoute
# Best practice: use Gateway API for new clusters (graduated to GA in K8s 1.29)
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: cilium
spec:
  controllerName: io.cilium/gateway-controller

---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: production-gateway
  namespace: infrastructure
spec:
  gatewayClassName: cilium
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      tls:
        mode: Terminate
        certificateRefs:
          - name: wildcard-tls
            namespace: infrastructure
      allowedRoutes:
        namespaces:
          from: Selector
          selector:
            matchLabels:
              gateway-access: "true"

---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-routes
  namespace: production
spec:
  parentRefs:
    - name: production-gateway
      namespace: infrastructure
  hostnames:
    - "api.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v2
      backendRefs:
        - name: api-server-v2
          port: 80
          weight: 90
        - name: api-server-v3
          port: 80
          weight: 10    # Canary traffic splitting
    - matches:
        - path:
            type: PathPrefix
            value: /v1
      backendRefs:
        - name: api-server-v1
          port: 80
```

The Gateway API is superior **because** it separates infrastructure concerns (GatewayClass, Gateway) from application routing (HTTPRoute), enabling platform teams and app teams to work independently. **Therefore**, new clusters should adopt Gateway API over Ingress.

## Networking Troubleshooting Toolkit

Debugging Kubernetes networking issues requires a systematic approach. Here are essential commands and techniques:

```bash
# Verify Pod-to-Pod connectivity across nodes
kubectl run netshoot --image=nicolaka/netshoot --rm -it -- bash
# Inside the pod:
# nslookup api-server.production.svc.cluster.local
# curl -v http://api-server.production.svc.cluster.local:80/health
# traceroute <pod-ip-on-another-node>

# Check if NetworkPolicies are blocking traffic
kubectl get networkpolicy -A
# Pitfall: NetworkPolicies are namespace-scoped; checking the wrong namespace
# shows nothing even when policies exist

# Verify CoreDNS is healthy
kubectl -n kube-system get pods -l k8s-app=kube-dns
kubectl -n kube-system logs -l k8s-app=kube-dns --tail=50

# Debug Service endpoints -- common mistake: selector labels don't match pod labels
kubectl get endpoints api-server -n production
# If endpoints list is empty, the selector doesn't match any running pods

# Check kube-proxy or eBPF rules
# For iptables-based kube-proxy:
# iptables-save | grep <service-cluster-ip>
# For Cilium eBPF:
kubectl exec -n kube-system ds/cilium -- cilium service list
```

**Best practice**: deploy a permanent debug pod (like `netshoot`) in each namespace for on-demand connectivity testing. **However**, the **trade-off** is that this increases the attack surface, so restrict access with RBAC and NetworkPolicies.

## Summary / Key Takeaways

- The Kubernetes flat networking model requires a **CNI plugin**; **Cilium** (eBPF) and **Calico** are the top production choices, each with distinct strengths
- **Services** abstract Pod endpoints; use ClusterIP for internal traffic, headless for StatefulSets, and LoadBalancer for external access. **Common mistake**: not understanding that headless services bypass kube-proxy entirely
- **NetworkPolicies** are default-allow until applied; the **pitfall** is that not all CNIs enforce them (Flannel does not), and policies are additive (you cannot deny traffic that another policy allows)
- **CoreDNS** handles cluster DNS; customize the Corefile for corporate DNS forwarding, caching tuning, and custom stub domains
- **Gateway API** replaces Ingress with role-oriented, multi-tenant L7 routing -- **best practice** for new deployments as it graduated to GA in Kubernetes 1.29
- **Common mistake**: not setting `timeoutSeconds` and `retryPolicy` on Ingress/HTTPRoute, causing cascading failures during backend outages
- **Therefore**, invest in understanding your CNI choice deeply -- it underpins every network interaction in the cluster and determines which features (NetworkPolicy, encryption, observability) are available
""",
    ),

    # --- 4. Resource Management and Scheduling ---
    (
        "kubernetes/resource-management-scheduling-qos",
        r"""Explain Kubernetes resource management and advanced scheduling including CPU and memory requests and limits, Quality of Service classes Guaranteed Burstable and BestEffort, PriorityClasses with preemption, topology spread constraints, node affinity and anti-affinity rules, and pod disruption budgets for safe rollouts""",
        r"""# Kubernetes Resource Management and Advanced Scheduling

## Why Resource Management Matters

In a shared Kubernetes cluster, resource management is the difference between stable, predictable workloads and cascading OOM kills at 3 AM. **Because** the Linux kernel's OOM killer is indiscriminate, Kubernetes provides a layered system of **requests**, **limits**, **QoS classes**, and **PriorityClasses** to control who gets resources and who gets evicted first. A **common mistake** is deploying workloads without resource specifications, leading to noisy-neighbor problems and unpredictable scheduling.

## Requests vs. Limits

**Requests** are what the scheduler uses to find a node with enough capacity. **Limits** are the ceiling the kubelet enforces via cgroups. The **trade-off**: setting requests too high wastes capacity (low utilization), setting them too low causes contention and OOM kills.

```yaml
# deployment-with-resources.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
    spec:
      containers:
        - name: api
          image: registry.example.com/api:v2.4.1
          resources:
            requests:
              cpu: "250m"       # 0.25 CPU cores -- scheduling guarantee
              memory: "512Mi"   # Scheduler reserves this on the node
            limits:
              cpu: "1000m"      # Can burst up to 1 core
              memory: "1Gi"     # Hard ceiling -- OOM killed if exceeded
              # Pitfall: CPU limits cause throttling even when node has spare CPU
              # Best practice: many teams now remove CPU limits entirely
              # and rely only on CPU requests for fair scheduling
          # Ephemeral storage limits (often forgotten)
          resources:
            requests:
              ephemeral-storage: "1Gi"
            limits:
              ephemeral-storage: "2Gi"
        - name: sidecar-proxy
          image: envoyproxy/envoy:v1.28
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "200m"
              memory: "256Mi"
```

### CPU Limits: The Great Debate

A **best practice** gaining traction is to **set CPU requests but not CPU limits**. This is **because** CPU is compressible -- the kernel throttles the process rather than killing it. **However**, CPU throttling introduces latency spikes that are invisible in standard monitoring. **Therefore**, if you keep CPU limits, use the `container_cpu_cfs_throttled_periods_total` Prometheus metric to detect throttling.

## Quality of Service (QoS) Classes

Kubernetes assigns one of three QoS classes to each Pod, determining eviction priority when a node is under memory pressure:

| QoS Class | Condition | Eviction Priority |
|-----------|-----------|-------------------|
| **Guaranteed** | All containers have equal requests and limits for CPU and memory | Last (lowest priority for eviction) |
| **Burstable** | At least one container has a request or limit set, but they are not equal | Middle |
| **BestEffort** | No requests or limits set on any container | First (highest priority for eviction) |

```yaml
# Guaranteed QoS -- requests MUST equal limits for ALL resources
apiVersion: v1
kind: Pod
metadata:
  name: guaranteed-pod
spec:
  containers:
    - name: app
      image: nginx:1.25
      resources:
        requests:
          cpu: "500m"
          memory: "256Mi"
        limits:
          cpu: "500m"       # Same as request
          memory: "256Mi"   # Same as request
      # This Pod gets QoS: Guaranteed
      # Best practice: use Guaranteed for databases, message brokers,
      # and anything where eviction causes data loss or long recovery
```

**Common mistake**: assuming BestEffort Pods are fine for development. They are the first to be evicted, and on a busy node, they may never get scheduled or run reliably.

## PriorityClasses and Preemption

**PriorityClasses** assign numeric priorities to Pods. When a high-priority Pod cannot be scheduled, the scheduler **preempts** (evicts) lower-priority Pods to make room.

```yaml
# priority-classes.yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: critical-production
value: 1000000
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: "For production services that must always run"

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: batch-processing
value: 100
globalDefault: false
preemptionPolicy: Never    # Never preempt others; wait for space
description: "For batch jobs that can tolerate delays"

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: default-priority
value: 500
globalDefault: true        # Applied to pods without explicit priority
description: "Default priority for standard workloads"
```

```yaml
# Using a PriorityClass in a Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  template:
    spec:
      priorityClassName: critical-production
      containers:
        - name: payment
          image: registry.example.com/payment:v3.1
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "500m"
              memory: "1Gi"
```

**Pitfall**: setting `preemptionPolicy: PreemptLowerPriority` on too many workloads causes cascading preemption storms. **Therefore**, use `Never` for batch jobs and reserve preemption for truly critical services.

## Topology Spread Constraints

Topology spread ensures Pods are distributed across failure domains (zones, nodes, racks) for high availability.

```yaml
# topology-spread.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-frontend
spec:
  replicas: 6
  template:
    metadata:
      labels:
        app: web-frontend
    spec:
      topologySpreadConstraints:
        # Spread evenly across availability zones
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: web-frontend
        # Also spread across nodes within each zone
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          # Trade-off: ScheduleAnyway allows imbalance when resources
          # are tight, preventing scheduling failures
          labelSelector:
            matchLabels:
              app: web-frontend
      # Node affinity -- prefer specific instance types
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node.kubernetes.io/instance-type
                    operator: In
                    values: ["m5.xlarge", "m5.2xlarge", "m6i.xlarge"]
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 80
              preference:
                matchExpressions:
                  - key: topology.kubernetes.io/zone
                    operator: In
                    values: ["us-east-1a", "us-east-1b"]
        # Pod anti-affinity -- don't co-locate with the cache
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: redis-cache
                topologyKey: kubernetes.io/hostname
      containers:
        - name: frontend
          image: registry.example.com/frontend:v4.0
```

## Pod Disruption Budgets

A **PodDisruptionBudget** (PDB) tells Kubernetes how many Pods of a given set must remain available during voluntary disruptions (node drains, cluster upgrades, autoscaler scale-downs). **Without PDBs**, a rolling node upgrade can take down all replicas simultaneously.

```yaml
# pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-server-pdb
  namespace: production
spec:
  # Option A: minimum available (use for services with known replica count)
  minAvailable: 2
  # Option B: maximum unavailable (better for autoscaled workloads)
  # maxUnavailable: 1
  # Pitfall: setting minAvailable equal to replicas blocks ALL disruptions
  # Common mistake: PDB selects wrong pods due to label mismatch
  selector:
    matchLabels:
      app: api-server

---
# For StatefulSets with exactly 3 replicas (quorum-based)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: etcd-pdb
spec:
  maxUnavailable: 1    # Never lose more than 1 of 3 (maintains quorum)
  selector:
    matchLabels:
      app: etcd
```

**Best practice**: every production Deployment and StatefulSet should have a PDB. **Therefore**, include PDB creation in your Helm charts and Kustomize overlays as standard. A **common mistake** is forgetting PDBs for StatefulSets that require quorum (etcd, ZooKeeper, Consul) -- without a PDB, a node drain can take down the entire quorum simultaneously, causing a complete outage.

### Interaction Between PDBs and Cluster Autoscaler

The **Cluster Autoscaler** respects PDBs when scaling down nodes. If draining a node would violate a PDB, the autoscaler skips that node. **However**, this can prevent scale-down entirely if PDBs are too restrictive. The **trade-off** is between workload protection and cost optimization. **Best practice**: use `maxUnavailable` instead of `minAvailable` for autoscaled workloads, **because** it adapts to the current replica count rather than requiring a fixed minimum.

## LimitRanges and ResourceQuotas

For multi-tenant clusters, use **LimitRanges** to set per-container defaults and **ResourceQuotas** to cap namespace-level consumption.

```yaml
# Namespace resource guardrails
apiVersion: v1
kind: LimitRange
metadata:
  name: container-limits
  namespace: team-alpha
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      max:
        cpu: "4"
        memory: "8Gi"
      min:
        cpu: "50m"
        memory: "64Mi"

---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-alpha-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "20"
    requests.memory: "40Gi"
    limits.cpu: "40"
    limits.memory: "80Gi"
    pods: "100"
    persistentvolumeclaims: "20"
```

## Summary / Key Takeaways

- **Requests** drive scheduling; **limits** drive enforcement. The **trade-off** is utilization vs. stability
- **QoS classes** (Guaranteed > Burstable > BestEffort) determine eviction order under memory pressure
- **PriorityClasses** enable preemption; use sparingly to avoid cascading eviction storms
- **Topology spread constraints** distribute Pods across zones and nodes for resilience
- **Pod Disruption Budgets** are mandatory for production workloads; **pitfall**: `minAvailable` equal to replica count blocks all maintenance
- **Best practice**: remove CPU limits for latency-sensitive services, monitor CFS throttling, and always set memory limits
- **Therefore**, resource management is not optional -- it is the foundation of cluster stability and the first thing to audit when workloads behave unpredictably
""",
    ),

    # --- 5. Kubernetes Security Hardening ---
    (
        "kubernetes/security-hardening-rbac-pss-supply-chain",
        r"""Describe comprehensive Kubernetes security hardening including RBAC design patterns with least privilege, Pod Security Standards replacing PodSecurityPolicy, seccomp and AppArmor profiles, network policy segmentation, secrets encryption at rest with KMS integration, and container supply chain security with image signing and admission policies""",
        r"""# Kubernetes Security Hardening: Defense in Depth

## The Kubernetes Attack Surface

Kubernetes clusters present a vast attack surface: the API server, etcd, kubelet, container runtime, network, and the supply chain (images, Helm charts, operators). Security hardening requires **defense in depth** -- multiple overlapping layers so that a breach in one layer is contained by the next. A **common mistake** is securing the perimeter (RBAC, network policies) while ignoring the runtime (seccomp, read-only filesystems) and supply chain (unsigned images).

## RBAC Design Patterns

**Role-Based Access Control** maps identities (users, service accounts) to permissions (verbs on API resources). The core principle is **least privilege**: grant the minimum permissions required and nothing more.

### Designing Roles with Least Privilege

```yaml
# rbac-developer-role.yaml
# Best practice: namespace-scoped Roles, not cluster-wide ClusterRoles
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: team-alpha
rules:
  # Can view most resources
  - apiGroups: ["", "apps", "batch"]
    resources: ["pods", "deployments", "jobs", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
  # Can manage deployments (but not delete)
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["create", "update", "patch"]
  # Can view logs and exec into pods (for debugging)
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create"]
    # Pitfall: pods/exec grants shell access -- equivalent to root in many cases
    # Trade-off: developers need debugging access, but exec is a privilege escalation vector
  # CANNOT access secrets directly
  # Common mistake: granting wildcard verbs ["*"] on all resources

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-binding
  namespace: team-alpha
subjects:
  - kind: Group
    name: "team-alpha-developers"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: developer
  apiGroup: rbac.authorization.k8s.io
```

```yaml
# Service account with minimal permissions for a controller
apiVersion: v1
kind: ServiceAccount
metadata:
  name: log-collector
  namespace: monitoring
  # Best practice: disable automounting the SA token unless needed
automountServiceAccountToken: false

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: log-collector-role
rules:
  - apiGroups: [""]
    resources: ["pods", "namespaces"]
    verbs: ["get", "list", "watch"]
  # Pitfall: using ClusterRole when a namespaced Role would suffice
  # However, log collectors genuinely need cluster-wide read access

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: log-collector-binding
subjects:
  - kind: ServiceAccount
    name: log-collector
    namespace: monitoring
roleRef:
  kind: ClusterRole
  name: log-collector-role
  apiGroup: rbac.authorization.k8s.io
```

### RBAC Audit Checklist

- **No wildcard verbs**: avoid `verbs: ["*"]` -- grant explicit verbs
- **No cluster-admin for humans**: use scoped roles, escalate through break-glass procedures
- **Aggregate ClusterRoles** for extensibility rather than monolithic roles
- **Common mistake**: binding the `system:masters` group, which bypasses all RBAC

## Pod Security Standards (Replacing PodSecurityPolicy)

**PodSecurityPolicy** was removed in Kubernetes 1.25. The replacement is **Pod Security Standards** (PSS) enforced by the built-in **Pod Security Admission** controller. Three profiles exist:

| Profile | Description | Use Case |
|---------|-------------|----------|
| **Privileged** | No restrictions | System-level workloads (CNI, monitoring agents) |
| **Baseline** | Prevents known privilege escalations | General workloads |
| **Restricted** | Maximum security lockdown | Sensitive/multi-tenant workloads |

```yaml
# Apply Pod Security Standards at namespace level
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Enforce restricted profile -- reject non-compliant pods
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
    # Warn on baseline violations (shows warnings to kubectl users)
    pod-security.kubernetes.io/warn: restricted
    # Audit logs for violations
    pod-security.kubernetes.io/audit: restricted

---
# A pod that complies with the 'restricted' profile
apiVersion: v1
kind: Pod
metadata:
  name: secure-app
  namespace: production
spec:
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/app:v2.0@sha256:abc123...
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
      # Best practice: read-only root filesystem forces proper volume usage
      # Trade-off: applications writing to /tmp need an emptyDir volume
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: "100Mi"
```

## Seccomp and AppArmor Profiles

**Seccomp** restricts which system calls a container can make. **AppArmor** restricts file access, network access, and capabilities. Together they form the runtime security layer.

```yaml
# Custom seccomp profile -- deployed to /var/lib/kubelet/seccomp/profiles/
# restricted-syscalls.json
# This goes on each node (use a DaemonSet or node provisioner)
apiVersion: v1
kind: ConfigMap
metadata:
  name: seccomp-profiles
  namespace: kube-system
data:
  restricted-syscalls.json: |
    {
      "defaultAction": "SCMP_ACT_ERRNO",
      "architectures": ["SCMP_ARCH_X86_64"],
      "syscalls": [
        {
          "names": [
            "read", "write", "open", "close", "stat", "fstat",
            "mmap", "mprotect", "munmap", "brk", "rt_sigaction",
            "rt_sigprocmask", "ioctl", "access", "pipe", "select",
            "sched_yield", "clone", "execve", "exit", "wait4",
            "kill", "fcntl", "flock", "fsync", "fdatasync",
            "getcwd", "chdir", "rename", "mkdir", "rmdir",
            "link", "unlink", "chmod", "chown", "umask",
            "gettimeofday", "getuid", "getgid", "geteuid", "getegid",
            "epoll_create1", "epoll_ctl", "epoll_wait",
            "socket", "connect", "accept", "bind", "listen",
            "sendto", "recvfrom", "setsockopt", "getsockopt",
            "getpeername", "getsockname", "futex", "set_robust_list",
            "nanosleep", "clock_gettime", "exit_group",
            "openat", "newfstatat", "readlinkat", "getrandom"
          ],
          "action": "SCMP_ACT_ALLOW"
        }
      ]
    }
```

```yaml
# Pod using custom seccomp profile
apiVersion: v1
kind: Pod
metadata:
  name: hardened-app
spec:
  securityContext:
    seccompProfile:
      type: Localhost
      localhostProfile: profiles/restricted-syscalls.json
  containers:
    - name: app
      image: registry.example.com/app:v2.0@sha256:abc123...
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
```

## Secrets Encryption at Rest

By default, Kubernetes stores Secrets in etcd **base64-encoded but not encrypted**. This is a critical **pitfall** -- anyone with etcd access can read all secrets. Enable encryption at rest with the API server encryption configuration.

```yaml
# encryption-config.yaml -- passed via --encryption-provider-config
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
      - configmaps   # Best practice: encrypt configmaps too
    providers:
      # KMS v2 provider -- integrates with AWS KMS, GCP KMS, Azure Key Vault
      # Best practice: use KMS rather than static keys because KMS provides
      # automatic key rotation and centralized audit logging
      - kms:
          apiVersion: v2
          name: aws-kms-provider
          endpoint: unix:///var/run/kmsplugin/socket.sock
          timeout: 3s
      # Fallback: identity provider (reads unencrypted data during migration)
      - identity: {}
```

```python
# scripts/verify_secret_encryption.py
# Verifies secrets are encrypted in etcd
import subprocess
import json
import sys
from typing import Optional

def check_etcd_encryption(namespace: str, secret_name: str) -> Optional[str]:
    # Read the raw secret from etcd using etcdctl
    # Best practice: run this as part of cluster security audits
    cmd = [
        "etcdctl",
        "--endpoints=https://127.0.0.1:2379",
        "--cacert=/etc/kubernetes/pki/etcd/ca.crt",
        "--cert=/etc/kubernetes/pki/etcd/server.crt",
        "--key=/etc/kubernetes/pki/etcd/server.key",
        "get",
        f"/registry/secrets/{namespace}/{secret_name}",
    ]
    result = subprocess.run(cmd, capture_output=True)
    raw_value = result.stdout

    # Encrypted secrets start with 'k8s:enc:kms:v2:' prefix
    # Unencrypted secrets start with 'k8s\x00'
    if b"k8s:enc:" in raw_value:
        return "ENCRYPTED"
    elif raw_value:
        return "NOT ENCRYPTED -- CRITICAL SECURITY ISSUE"
    return None

def audit_all_secrets() -> dict[str, str]:
    # Pitfall: forgetting to re-encrypt existing secrets after enabling encryption
    # Run: kubectl get secrets --all-namespaces -o json | \
    #      kubectl replace -f -
    # This forces re-encryption of all existing secrets
    results: dict[str, str] = {}
    cmd = ["kubectl", "get", "secrets", "--all-namespaces", "-o", "json"]
    output = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(output.stdout)
    for item in data.get("items", []):
        ns = item["metadata"]["namespace"]
        name = item["metadata"]["name"]
        status = check_etcd_encryption(ns, name)
        if status:
            results[f"{ns}/{name}"] = status
    return results

if __name__ == "__main__":
    results = audit_all_secrets()
    for secret, status in results.items():
        indicator = "[OK]" if "ENCRYPTED" == status else "[FAIL]"
        print(f"  {indicator} {secret}: {status}")
    failures = [s for s, st in results.items() if "NOT" in st]
    if failures:
        print(f"\nCRITICAL: {len(failures)} unencrypted secrets found!")
        sys.exit(1)
```

## Container Supply Chain Security

Supply chain attacks target the images you deploy. **Best practice**: sign images, verify signatures at admission, scan for vulnerabilities, and pin digests instead of tags.

```yaml
# Kyverno policy to enforce image signing with cosign/Sigstore
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signatures
spec:
  validationFailureAction: Enforce
  webhookTimeoutSeconds: 10
  rules:
    - name: verify-cosign-signature
      match:
        any:
          - resources:
              kinds:
                - Pod
      verifyImages:
        - imageReferences:
            - "registry.example.com/*"
          attestors:
            - entries:
                - keys:
                    publicKeys: |-
                      -----BEGIN PUBLIC KEY-----
                      MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
                      -----END PUBLIC KEY-----
          # Require SBOM attestation
          attestations:
            - type: https://spdx.dev/Document
              conditions:
                - all:
                    - key: "{{ creationInfo.created }}"
                      operator: NotEquals
                      value: ""
    - name: require-digest-not-tag
      match:
        any:
          - resources:
              kinds:
                - Pod
      validate:
        message: "Images must use digest references (@sha256:...), not tags"
        pattern:
          spec:
            containers:
              - image: "*@sha256:*"
            # Therefore: pinning digests prevents tag mutation attacks
            # Common mistake: using :latest or mutable tags in production
```

### Multi-Layer Security Architecture

```
Layer 1: Supply Chain     -- Image signing, SBOM, vulnerability scanning
Layer 2: Admission        -- RBAC, Pod Security Standards, Kyverno/Gatekeeper
Layer 3: Network          -- NetworkPolicies, service mesh mTLS
Layer 4: Runtime          -- Seccomp, AppArmor, read-only filesystems
Layer 5: Secrets          -- Encryption at rest, external secret stores (Vault)
Layer 6: Audit            -- API audit logging, Falco runtime detection
```

**However**, implementing all layers simultaneously is overwhelming. **Therefore**, prioritize in this order: RBAC (immediate), Pod Security Standards (quick win), NetworkPolicies (high impact), secrets encryption (critical data protection), then supply chain and runtime hardening.

## Summary / Key Takeaways

- **RBAC** must follow least privilege: no wildcards, namespace-scoped Roles over ClusterRoles, disable SA token automounting
- **Pod Security Standards** (Restricted profile) replace PodSecurityPolicy; enforce at the namespace level with labels
- **Seccomp** profiles restrict system calls; the `RuntimeDefault` profile blocks 44+ dangerous syscalls with zero configuration
- **Secrets encryption at rest** with KMS is non-negotiable; **pitfall**: base64 encoding is NOT encryption
- **Supply chain security** requires image signing (cosign/Sigstore), digest pinning, and admission policies; the **common mistake** is trusting mutable tags
- **Best practice**: adopt defense in depth -- no single layer is sufficient, **because** attackers will find the weakest link
- **Therefore**, security hardening is an ongoing process: audit RBAC quarterly, scan images continuously, rotate secrets, and test policies in staging before enforcing in production
""",
    ),
]
