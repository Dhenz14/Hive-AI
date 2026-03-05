"""
Batch P4 — Kubernetes: Operators, CRDs, scheduling, service mesh.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Kubernetes Operators ---
    (
        "kubernetes_operator_pattern",
        "Explain the Kubernetes Operator pattern — custom resources, controllers, reconciliation "
        "loops, and how to build a production operator using kubebuilder. Show a complete operator "
        "that manages a database cluster with automatic failover, backup scheduling, and scaling. "
        "Include Go code with proper error handling, status management, and testing.",
        """\
# Kubernetes Operators: Automating Complex Stateful Workloads

## What is an Operator?

A Kubernetes Operator extends the Kubernetes API with **domain-specific knowledge** — it
encodes the operational expertise of a human operator into software. Instead of a DBA
manually performing database failover, backup, and scaling, the operator does it automatically.

```
Without Operator:
  DBA monitors DB → detects failure → manually promotes replica → updates config
  Time: 5-30 minutes, human error risk

With Operator:
  Operator watches CRD → detects failure → promotes replica → updates endpoints
  Time: 5-30 seconds, deterministic
```

The Operator pattern has three components:
1. **Custom Resource Definition (CRD)**: Extends the K8s API with your domain object
2. **Controller**: Watches CRDs and reconciles actual state with desired state
3. **Reconciliation loop**: The core logic — called whenever the resource changes

## Custom Resource Definition

```yaml
# api/v1alpha1/database_types.go → generates this CRD
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: databases.myorg.io
spec:
  group: myorg.io
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: ["replicas", "storage"]
              properties:
                replicas:
                  type: integer
                  minimum: 1
                  maximum: 7
                engine:
                  type: string
                  enum: ["postgres", "mysql"]
                  default: "postgres"
                version:
                  type: string
                  default: "16"
                storage:
                  type: object
                  properties:
                    size:
                      type: string
                      default: "10Gi"
                    storageClass:
                      type: string
                backup:
                  type: object
                  properties:
                    schedule:
                      type: string
                      default: "0 2 * * *"
                    retention:
                      type: integer
                      default: 7
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: ["Pending", "Creating", "Running", "Failing", "Deleting"]
                replicas:
                  type: integer
                readyReplicas:
                  type: integer
                primaryEndpoint:
                  type: string
                lastBackup:
                  type: string
                  format: date-time
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type: { type: string }
                      status: { type: string }
                      reason: { type: string }
                      message: { type: string }
                      lastTransitionTime: { type: string }
      subresources:
        status: {}  # Enable status subresource
        scale:
          specReplicasPath: .spec.replicas
          statusReplicasPath: .status.replicas
      additionalPrinterColumns:
        - name: Phase
          type: string
          jsonPath: .status.phase
        - name: Replicas
          type: integer
          jsonPath: .status.readyReplicas
        - name: Primary
          type: string
          jsonPath: .status.primaryEndpoint
  scope: Namespaced
  names:
    plural: databases
    singular: database
    kind: Database
    shortNames: ["db"]
```

## Go Type Definitions

```go
package v1alpha1

import (
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// DatabaseSpec defines the desired state of Database.
type DatabaseSpec struct {
    Replicas int32          `json:"replicas"`
    Engine   string         `json:"engine,omitempty"`
    Version  string         `json:"version,omitempty"`
    Storage  StorageSpec    `json:"storage"`
    Backup   *BackupSpec    `json:"backup,omitempty"`
}

type StorageSpec struct {
    Size         string `json:"size"`
    StorageClass string `json:"storageClass,omitempty"`
}

type BackupSpec struct {
    Schedule  string `json:"schedule,omitempty"`
    Retention int32  `json:"retention,omitempty"`
}

// DatabaseStatus defines the observed state of Database.
type DatabaseStatus struct {
    Phase           string             `json:"phase,omitempty"`
    Replicas        int32              `json:"replicas,omitempty"`
    ReadyReplicas   int32              `json:"readyReplicas,omitempty"`
    PrimaryEndpoint string             `json:"primaryEndpoint,omitempty"`
    LastBackup      *metav1.Time       `json:"lastBackup,omitempty"`
    Conditions      []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:subresource:scale:specpath=.spec.replicas,statuspath=.status.replicas
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Ready",type=integer,JSONPath=`.status.readyReplicas`

// Database is the Schema for the databases API.
type Database struct {
    metav1.TypeMeta   `json:",inline"`
    metav1.ObjectMeta `json:"metadata,omitempty"`

    Spec   DatabaseSpec   `json:"spec,omitempty"`
    Status DatabaseStatus `json:"status,omitempty"`
}
```

## Reconciliation Controller

```go
package controllers

import (
    "context"
    "fmt"
    "time"

    appsv1 "k8s.io/api/apps/v1"
    corev1 "k8s.io/api/core/v1"
    "k8s.io/apimachinery/pkg/api/errors"
    "k8s.io/apimachinery/pkg/api/meta"
    "k8s.io/apimachinery/pkg/api/resource"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/runtime"
    "k8s.io/apimachinery/pkg/types"
    ctrl "sigs.k8s.io/controller-runtime"
    "sigs.k8s.io/controller-runtime/pkg/client"
    "sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
    "sigs.k8s.io/controller-runtime/pkg/log"

    dbv1alpha1 "myorg.io/db-operator/api/v1alpha1"
)

const databaseFinalizer = "myorg.io/database-finalizer"

// DatabaseReconciler reconciles a Database object.
type DatabaseReconciler struct {
    client.Client
    Scheme *runtime.Scheme
}

// Reconcile is the core loop — called whenever a Database resource changes.
//
// The reconciliation pattern is DECLARATIVE, not imperative:
// 1. Read the desired state (Database spec)
// 2. Read the actual state (StatefulSet, Services, PVCs)
// 3. Compute the diff
// 4. Apply changes to converge actual → desired
//
// This function must be IDEMPOTENT — calling it multiple times with the
// same input must produce the same result. This is critical because the
// controller runtime may call Reconcile multiple times for the same event.
func (r *DatabaseReconciler) Reconcile(
    ctx context.Context,
    req ctrl.Request,
) (ctrl.Result, error) {
    logger := log.FromContext(ctx)

    // 1. Fetch the Database resource
    var db dbv1alpha1.Database
    if err := r.Get(ctx, req.NamespacedName, &db); err != nil {
        if errors.IsNotFound(err) {
            return ctrl.Result{}, nil // Resource deleted, nothing to do
        }
        return ctrl.Result{}, fmt.Errorf("fetching database: %w", err)
    }

    // 2. Handle deletion with finalizer
    if !db.DeletionTimestamp.IsZero() {
        return r.handleDeletion(ctx, &db)
    }

    // Add finalizer if not present
    if !controllerutil.ContainsFinalizer(&db, databaseFinalizer) {
        controllerutil.AddFinalizer(&db, databaseFinalizer)
        if err := r.Update(ctx, &db); err != nil {
            return ctrl.Result{}, err
        }
    }

    // 3. Reconcile each sub-resource
    // Order matters: Service before StatefulSet (so pods can find each other)
    if err := r.reconcileService(ctx, &db); err != nil {
        return r.setFailing(ctx, &db, "ServiceFailed", err)
    }

    if err := r.reconcileStatefulSet(ctx, &db); err != nil {
        return r.setFailing(ctx, &db, "StatefulSetFailed", err)
    }

    // 4. Update status based on actual state
    if err := r.updateStatus(ctx, &db); err != nil {
        return ctrl.Result{}, err
    }

    // 5. Requeue after 30s for periodic health checks
    return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

func (r *DatabaseReconciler) reconcileStatefulSet(
    ctx context.Context,
    db *dbv1alpha1.Database,
) error {
    logger := log.FromContext(ctx)

    desired := r.desiredStatefulSet(db)

    // Set owner reference — when Database is deleted, StatefulSet is garbage collected
    if err := controllerutil.SetControllerReference(db, desired, r.Scheme); err != nil {
        return fmt.Errorf("setting owner reference: %w", err)
    }

    // CreateOrUpdate — the idempotent operation
    var existing appsv1.StatefulSet
    err := r.Get(ctx, types.NamespacedName{
        Name: desired.Name, Namespace: desired.Namespace,
    }, &existing)

    if errors.IsNotFound(err) {
        logger.Info("creating StatefulSet", "name", desired.Name)
        return r.Create(ctx, desired)
    }
    if err != nil {
        return fmt.Errorf("fetching StatefulSet: %w", err)
    }

    // Update if spec changed
    existing.Spec.Replicas = desired.Spec.Replicas
    existing.Spec.Template = desired.Spec.Template
    return r.Update(ctx, &existing)
}

func (r *DatabaseReconciler) desiredStatefulSet(
    db *dbv1alpha1.Database,
) *appsv1.StatefulSet {
    labels := map[string]string{
        "app":                          "database",
        "myorg.io/database":            db.Name,
        "app.kubernetes.io/managed-by": "db-operator",
    }

    return &appsv1.StatefulSet{
        ObjectMeta: metav1.ObjectMeta{
            Name:      db.Name,
            Namespace: db.Namespace,
            Labels:    labels,
        },
        Spec: appsv1.StatefulSetSpec{
            Replicas:    &db.Spec.Replicas,
            ServiceName: db.Name + "-headless",
            Selector: &metav1.LabelSelector{
                MatchLabels: labels,
            },
            Template: corev1.PodTemplateSpec{
                ObjectMeta: metav1.ObjectMeta{Labels: labels},
                Spec: corev1.PodSpec{
                    Containers: []corev1.Container{
                        {
                            Name:  "postgres",
                            Image: fmt.Sprintf("postgres:%s", db.Spec.Version),
                            Ports: []corev1.ContainerPort{
                                {Name: "postgres", ContainerPort: 5432},
                            },
                            Resources: corev1.ResourceRequirements{
                                Requests: corev1.ResourceList{
                                    corev1.ResourceCPU:    resource.MustParse("250m"),
                                    corev1.ResourceMemory: resource.MustParse("512Mi"),
                                },
                                Limits: corev1.ResourceList{
                                    corev1.ResourceCPU:    resource.MustParse("1"),
                                    corev1.ResourceMemory: resource.MustParse("2Gi"),
                                },
                            },
                            ReadinessProbe: &corev1.Probe{
                                ProbeHandler: corev1.ProbeHandler{
                                    Exec: &corev1.ExecAction{
                                        Command: []string{"pg_isready", "-U", "postgres"},
                                    },
                                },
                                InitialDelaySeconds: 10,
                                PeriodSeconds:       5,
                            },
                            VolumeMounts: []corev1.VolumeMount{
                                {Name: "data", MountPath: "/var/lib/postgresql/data"},
                            },
                        },
                    },
                },
            },
            VolumeClaimTemplates: []corev1.PersistentVolumeClaim{
                {
                    ObjectMeta: metav1.ObjectMeta{Name: "data"},
                    Spec: corev1.PersistentVolumeClaimSpec{
                        AccessModes: []corev1.PersistentVolumeAccessMode{
                            corev1.ReadWriteOnce,
                        },
                        Resources: corev1.VolumeResourceRequirements{
                            Requests: corev1.ResourceList{
                                corev1.ResourceStorage: resource.MustParse(db.Spec.Storage.Size),
                            },
                        },
                    },
                },
            },
        },
    }
}

func (r *DatabaseReconciler) handleDeletion(
    ctx context.Context,
    db *dbv1alpha1.Database,
) (ctrl.Result, error) {
    logger := log.FromContext(ctx)

    if controllerutil.ContainsFinalizer(db, databaseFinalizer) {
        // Perform cleanup: take final backup, remove monitoring, etc.
        logger.Info("performing cleanup before deletion")

        // Remove finalizer to allow Kubernetes to delete the resource
        controllerutil.RemoveFinalizer(db, databaseFinalizer)
        if err := r.Update(ctx, db); err != nil {
            return ctrl.Result{}, err
        }
    }

    return ctrl.Result{}, nil
}

func (r *DatabaseReconciler) updateStatus(
    ctx context.Context,
    db *dbv1alpha1.Database,
) error {
    // Count ready pods
    var sts appsv1.StatefulSet
    if err := r.Get(ctx, types.NamespacedName{
        Name: db.Name, Namespace: db.Namespace,
    }, &sts); err != nil {
        return err
    }

    db.Status.Replicas = sts.Status.Replicas
    db.Status.ReadyReplicas = sts.Status.ReadyReplicas

    if sts.Status.ReadyReplicas == *sts.Spec.Replicas {
        db.Status.Phase = "Running"
        meta.SetStatusCondition(&db.Status.Conditions, metav1.Condition{
            Type:    "Available",
            Status:  metav1.ConditionTrue,
            Reason:  "AllReplicasReady",
            Message: fmt.Sprintf("%d/%d replicas ready", sts.Status.ReadyReplicas, *sts.Spec.Replicas),
        })
    } else {
        db.Status.Phase = "Creating"
    }

    db.Status.PrimaryEndpoint = fmt.Sprintf("%s-0.%s-headless.%s.svc.cluster.local:5432",
        db.Name, db.Name, db.Namespace)

    return r.Status().Update(ctx, db)
}

func (r *DatabaseReconciler) setFailing(
    ctx context.Context,
    db *dbv1alpha1.Database,
    reason string,
    err error,
) (ctrl.Result, error) {
    db.Status.Phase = "Failing"
    meta.SetStatusCondition(&db.Status.Conditions, metav1.Condition{
        Type:    "Available",
        Status:  metav1.ConditionFalse,
        Reason:  reason,
        Message: err.Error(),
    })
    _ = r.Status().Update(ctx, db)
    return ctrl.Result{RequeueAfter: 10 * time.Second}, err
}

// SetupWithManager registers the controller with the manager.
func (r *DatabaseReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&dbv1alpha1.Database{}).
        Owns(&appsv1.StatefulSet{}).  // Watch owned StatefulSets
        Owns(&corev1.Service{}).       // Watch owned Services
        Complete(r)
}
```

## Testing the Operator

```go
package controllers_test

import (
    "context"
    "testing"
    "time"

    . "github.com/onsi/ginkgo/v2"
    . "github.com/onsi/gomega"
    appsv1 "k8s.io/api/apps/v1"
    metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
    "k8s.io/apimachinery/pkg/types"
    "sigs.k8s.io/controller-runtime/pkg/client"

    dbv1alpha1 "myorg.io/db-operator/api/v1alpha1"
)

var _ = Describe("Database Controller", func() {
    const timeout = 30 * time.Second
    const interval = 1 * time.Second

    ctx := context.Background()

    It("should create a StatefulSet when Database is created", func() {
        db := &dbv1alpha1.Database{
            ObjectMeta: metav1.ObjectMeta{
                Name:      "test-db",
                Namespace: "default",
            },
            Spec: dbv1alpha1.DatabaseSpec{
                Replicas: 3,
                Engine:   "postgres",
                Version:  "16",
                Storage:  dbv1alpha1.StorageSpec{Size: "10Gi"},
            },
        }

        Expect(k8sClient.Create(ctx, db)).To(Succeed())

        // Verify StatefulSet is created
        var sts appsv1.StatefulSet
        Eventually(func() error {
            return k8sClient.Get(ctx, types.NamespacedName{
                Name: "test-db", Namespace: "default",
            }, &sts)
        }, timeout, interval).Should(Succeed())

        Expect(*sts.Spec.Replicas).To(Equal(int32(3)))
    })

    It("should scale when replicas are updated", func() {
        var db dbv1alpha1.Database
        Expect(k8sClient.Get(ctx, types.NamespacedName{
            Name: "test-db", Namespace: "default",
        }, &db)).To(Succeed())

        db.Spec.Replicas = 5
        Expect(k8sClient.Update(ctx, &db)).To(Succeed())

        Eventually(func() int32 {
            var sts appsv1.StatefulSet
            k8sClient.Get(ctx, types.NamespacedName{
                Name: "test-db", Namespace: "default",
            }, &sts)
            return *sts.Spec.Replicas
        }, timeout, interval).Should(Equal(int32(5)))
    })
})
```

## Key Takeaways

The Operator pattern is the correct way to manage stateful workloads on Kubernetes because
it encodes operational knowledge into software that runs 24/7. The common mistake is building
operators for stateless applications — those don't need operators, a Deployment is sufficient.
Operators add value for databases, message queues, monitoring stacks, and other stateful
systems where the operational complexity justifies the engineering investment.

The most important design principle is **idempotency** — the Reconcile function must produce
the same result regardless of how many times it's called. This is the trade-off compared to
imperative scripts: operators are harder to write but much more reliable because they
continuously reconcile toward the desired state, automatically recovering from failures
that would require manual intervention with scripts.

For production operators, always use finalizers for cleanup, owner references for garbage
collection, status conditions for observability, and the controller-runtime library for
the reconciliation framework. Avoid writing custom watch/event handling — the framework
handles this correctly, including rate limiting and exponential backoff.
"""
    ),

    # --- 2. Kubernetes Scheduling and Resource Management ---
    (
        "kubernetes_scheduling_resource_management",
        "Explain Kubernetes scheduling internals — how the scheduler places pods, scoring plugins, "
        "topology spread constraints, pod priority and preemption, resource quotas, and limit ranges. "
        "Show how to configure a multi-tenant cluster with fair resource sharing, GPU scheduling, "
        "and custom scheduling profiles. Include YAML manifests and explain production trade-offs.",
        """\
# Kubernetes Scheduling: How Pods Get Placed and Resources Get Managed

## How the Scheduler Works

The Kubernetes scheduler is a **two-phase** system:

```
Pod needs scheduling:
  Phase 1: FILTERING (eliminate nodes that can't run the pod)
    ├── NodeResourcesFit: does node have enough CPU/memory?
    ├── PodTopologySpread: does this violate spread constraints?
    ├── NodeAffinity: does node match required labels?
    ├── TaintToleration: does pod tolerate node taints?
    └── ... 20+ filter plugins

  Phase 2: SCORING (rank remaining nodes 0-100)
    ├── NodeResourcesBalancedAllocation: prefer balanced CPU/memory usage
    ├── ImageLocality: prefer nodes that already have the container image
    ├── InterPodAffinity: prefer nodes near related pods
    └── ... weighted scoring plugins

  Result: Pod → highest-scoring node
```

**Key insight**: Filtering is cheap (eliminates impossible nodes) while scoring is expensive
(evaluates all remaining nodes). This is why the scheduler has a `percentageOfNodesToScore`
parameter — in large clusters (1000+ nodes), scoring every node is too slow, so it scores
a percentage and picks the best from that sample.

## Production Multi-Tenant Configuration

```yaml
# ResourceQuota — limits total resources per namespace
# This prevents one team from consuming all cluster resources
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-alpha-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "20"           # Max 20 CPU cores requested
    requests.memory: "40Gi"      # Max 40GB memory requested
    limits.cpu: "40"             # Max 40 CPU cores limit
    limits.memory: "80Gi"
    pods: "100"                  # Max 100 pods
    persistentvolumeclaims: "20"
    requests.nvidia.com/gpu: "4" # Max 4 GPUs
    services.loadbalancers: "2"  # Max 2 LoadBalancer services (cost control)

---
# LimitRange — default and max per-container limits
# Without this, developers can request 100 CPU cores in a single pod
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: team-alpha
spec:
  limits:
    - type: Container
      default:          # Applied if pod doesn't specify limits
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:   # Applied if pod doesn't specify requests
        cpu: "100m"
        memory: "128Mi"
      max:              # Hard cap per container
        cpu: "4"
        memory: "8Gi"
        nvidia.com/gpu: "1"
      min:              # Minimum to prevent trivial pods
        cpu: "50m"
        memory: "64Mi"
    - type: PersistentVolumeClaim
      max:
        storage: "100Gi"

---
# PriorityClass — determines which pods get preempted under pressure
# Critical for multi-tenant: production workloads should survive over batch jobs
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: production-critical
value: 1000000     # Higher = more important
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: "Production workloads — will preempt batch jobs if resources needed"

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: batch-processing
value: 100000
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: "Batch jobs — can be preempted by production workloads"

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: best-effort
value: 0
globalDefault: true  # Default for pods without priority class
preemptionPolicy: Never  # Never preempt other pods
description: "Development/testing — evicted first under resource pressure"
```

## Topology Spread Constraints

```yaml
# Spread pods across availability zones AND nodes
# This is critical for HA — losing one zone shouldn't take down your service
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  replicas: 6
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
    spec:
      # Priority: production workloads survive preemption
      priorityClassName: production-critical

      topologySpreadConstraints:
        # Spread across zones — hard requirement
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule  # Fail rather than cluster in one zone
          labelSelector:
            matchLabels:
              app: api-server
          # With 6 replicas and 3 zones: 2 per zone (maxSkew=1 means difference ≤1)

        # Spread across nodes — soft preference
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway  # Best effort on node spread
          labelSelector:
            matchLabels:
              app: api-server

      # Affinity: prefer nodes with SSD storage
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 80
              preference:
                matchExpressions:
                  - key: disktype
                    operator: In
                    values: ["ssd"]

        # Anti-affinity: don't schedule with the database (resource contention)
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values: ["postgresql"]
              topologyKey: kubernetes.io/hostname

      containers:
        - name: api
          image: myorg/api:v2.1.0
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
```

## GPU Scheduling

```yaml
# GPU-enabled workload — requires NVIDIA device plugin
apiVersion: batch/v1
kind: Job
metadata:
  name: model-training
  namespace: ml-team
spec:
  template:
    spec:
      priorityClassName: batch-processing
      restartPolicy: OnFailure
      # Node selector for GPU nodes
      nodeSelector:
        accelerator: nvidia-a100

      # Tolerations for GPU node taints
      tolerations:
        - key: "nvidia.com/gpu"
          operator: "Exists"
          effect: "NoSchedule"

      containers:
        - name: trainer
          image: myorg/model-trainer:latest
          resources:
            requests:
              nvidia.com/gpu: 2  # Request 2 GPUs
              cpu: "8"
              memory: "32Gi"
            limits:
              nvidia.com/gpu: 2  # Must match request (GPUs are not overcommittable)
              cpu: "16"
              memory: "64Gi"
          env:
            - name: CUDA_VISIBLE_DEVICES
              value: "0,1"
          volumeMounts:
            - name: training-data
              mountPath: /data
              readOnly: true
            - name: model-output
              mountPath: /output

      volumes:
        - name: training-data
          persistentVolumeClaim:
            claimName: training-dataset
        - name: model-output
          persistentVolumeClaim:
            claimName: model-output-pvc

---
# Time-sharing GPUs with MIG (Multi-Instance GPU)
# A single A100 can be partitioned into up to 7 GPU instances
apiVersion: v1
kind: Pod
metadata:
  name: inference-server
spec:
  containers:
    - name: model-server
      image: myorg/vllm-server:latest
      resources:
        requests:
          nvidia.com/mig-3g.20gb: 1  # One MIG partition (3 compute, 20GB VRAM)
        limits:
          nvidia.com/mig-3g.20gb: 1
```

## Custom Scheduling Profile

```yaml
# For clusters that need different scheduling behavior for different workloads
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  # Default profile for most workloads
  - schedulerName: default-scheduler
    plugins:
      score:
        enabled:
          - name: NodeResourcesBalancedAllocation
            weight: 1
          - name: ImageLocality
            weight: 1
          - name: InterPodAffinity
            weight: 2  # Prefer co-located pods

  # Bin-packing profile for batch workloads
  # Packs pods tightly to minimize node count (save cost)
  - schedulerName: bin-packing-scheduler
    plugins:
      score:
        enabled:
          - name: NodeResourcesFit
            weight: 1
        disabled:
          - name: NodeResourcesBalancedAllocation
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated  # Prefer nodes that are already busy
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
```

## Understanding Resource Requests vs Limits

```
Requests vs Limits — the most misunderstood Kubernetes concept:

REQUESTS = guaranteed resources (used for scheduling)
  - Scheduler uses requests to find nodes with enough capacity
  - cgroups reserve this amount for the pod
  - If a node has 4 CPU and 3 CPU is requested by other pods, only 1 CPU is available

LIMITS = maximum resources (enforced at runtime)
  - CPU: pod is throttled (not killed) if it exceeds the limit
  - Memory: pod is OOM-killed if it exceeds the limit

Common mistakes:
  1. Setting limits = requests (no burstability, wastes resources)
  2. Not setting requests at all (scheduler has no info, pods pile up)
  3. Setting very high limits (one pod can starve others)

Best practice for production:
  requests.cpu:    50-80% of expected average usage
  limits.cpu:      2-4x requests (allow bursts)
  requests.memory: expected peak usage (memory is not compressible)
  limits.memory:   requests + 10-20% safety margin

  Why different strategies for CPU vs memory?
  CPU is compressible — throttling is annoying but not fatal
  Memory is NOT compressible — exceeding the limit = OOM kill = downtime
```

## Key Takeaways

Kubernetes scheduling is a balance between **utilization** (pack pods tightly to save cost)
and **availability** (spread pods across failure domains). The common mistake is optimizing
only for one — tight packing saves money until a node fails and takes down all your replicas.

For production multi-tenant clusters, the essential configuration is: ResourceQuotas per
namespace (prevent resource hogging), LimitRanges (sane defaults), PriorityClasses (protect
production from batch), and TopologySpreadConstraints (survive zone failures). The trade-off
is operational complexity — each of these features requires monitoring and tuning, but without
them, multi-tenant clusters inevitably suffer from noisy-neighbor problems.

GPU scheduling deserves special attention because GPUs are expensive and cannot be
overcommitted. Use node taints and tolerations to dedicate GPU nodes, NVIDIA MIG for
sharing A100s, and batch scheduling with preemption to maximize GPU utilization.
"""
    ),
]
