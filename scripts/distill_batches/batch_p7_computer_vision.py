"""
Batch P7 — Computer Vision Techniques
Covers: CNN architectures, object detection, segmentation, Vision Transformers, self-supervised learning.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "cv/cnn-architectures-deep-dive",
        "Explain convolutional neural network architectures in depth including ResNet skip connections, EfficientNet compound scaling, and ConvNeXt modernization, and implement a complete ResNet-18 from scratch in PyTorch with residual blocks, batch normalization, skip connections, receptive field calculation, and parameter counting.",
        r"""# Convolutional Neural Network Architectures: A Deep Dive

## The Evolution of CNN Design

Modern convolutional neural networks have evolved dramatically since AlexNet won ImageNet in 2012. Understanding **why** each architectural innovation was introduced is critical, because each solved a specific failure mode of its predecessor. The progression from VGG to ResNet to EfficientNet to ConvNeXt reveals a fascinating interplay between empirical intuition and principled design.

**The core insight** driving all CNN design is that depth enables abstraction: early layers learn edges and textures, middle layers learn parts and patterns, and deep layers learn semantic concepts. However, simply stacking more layers causes **vanishing gradients**, **degradation problems**, and **computational explosion** — each addressed by different architectural innovations.

## ResNet: Skip Connections and Residual Learning

### The Degradation Problem

Before ResNet, researchers observed a counterintuitive phenomenon: deeper networks performed **worse** than shallow ones on both training and test sets. This was not overfitting — training error also increased. Therefore, the problem was not generalization but **optimization**. Deep networks are harder to optimize because gradients must flow through dozens of nonlinear layers.

**Common mistake**: Confusing the degradation problem with vanishing gradients. While related, they are distinct. Vanishing gradients prevent learning entirely; degradation means the network converges to a worse solution than a shallower one.

### Residual Blocks

The key idea is deceptively simple: instead of learning a mapping `H(x)`, learn the **residual** `F(x) = H(x) - x`, so the output becomes `F(x) + x`. This skip connection (also called a shortcut or identity mapping) provides a gradient highway that bypasses the nonlinear layers, making optimization dramatically easier.

**Best practice**: Use **pre-activation** residual blocks (BN -> ReLU -> Conv) rather than post-activation (Conv -> BN -> ReLU) for networks deeper than 50 layers, because pre-activation enables cleaner gradient flow through the identity path.

### Full ResNet-18 Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Type


class ResidualBlock(nn.Module):
    # Basic residual block with two 3x3 convolutions
    # Uses pre-activation style for clarity

    expansion: int = 1

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        stride: int = 1,
        downsample: Optional[nn.Module] = None,
    ) -> None:
        super().__init__()
        # First convolution — may downsample spatially via stride
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, kernel_size=3,
            stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)

        # Second convolution — always preserves spatial dims
        self.conv2 = nn.Conv2d(
            out_channels, out_channels, kernel_size=3,
            stride=1, padding=1, bias=False
        )
        self.bn2 = nn.BatchNorm2d(out_channels)

        # Downsample shortcut when dimensions change
        self.downsample = downsample
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        # The skip connection — this is the key innovation
        # When spatial dimensions or channel count changes,
        # we project the identity to match via 1x1 conv
        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity  # Element-wise addition of residual
        out = self.relu(out)
        return out


class ResNet18(nn.Module):
    # Full ResNet-18 implementation for ImageNet classification
    # Architecture: conv7x7 -> 4 stages of residual blocks -> avgpool -> fc
    # Total: 1 + 2*4*2 + 1 = 18 layers (counting conv layers only)

    def __init__(self, num_classes: int = 1000) -> None:
        super().__init__()

        self.in_channels = 64

        # Stem: aggressive downsampling from 224x224 to 56x56
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        # Four residual stages — each doubles channels, halves spatial dims
        self.layer1 = self._make_layer(64, blocks=2, stride=1)   # 56x56
        self.layer2 = self._make_layer(128, blocks=2, stride=2)  # 28x28
        self.layer3 = self._make_layer(256, blocks=2, stride=2)  # 14x14
        self.layer4 = self._make_layer(512, blocks=2, stride=2)  # 7x7

        # Classification head
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(512, num_classes)

        # Weight initialization — critical for convergence
        self._initialize_weights()

    def _make_layer(self, out_channels: int, blocks: int, stride: int) -> nn.Sequential:
        downsample = None
        if stride != 1 or self.in_channels != out_channels:
            # 1x1 conv projection to match dimensions
            downsample = nn.Sequential(
                nn.Conv2d(self.in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

        layers: List[nn.Module] = []
        # First block handles downsampling
        layers.append(ResidualBlock(self.in_channels, out_channels, stride, downsample))
        self.in_channels = out_channels
        # Remaining blocks maintain dimensions
        for _ in range(1, blocks):
            layers.append(ResidualBlock(out_channels, out_channels))

        return nn.Sequential(*layers)

    def _initialize_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Stem
        x = self.conv1(x)       # 224 -> 112
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)     # 112 -> 56

        # Residual stages
        x = self.layer1(x)      # 56 -> 56 (no downsampling)
        x = self.layer2(x)      # 56 -> 28
        x = self.layer3(x)      # 28 -> 14
        x = self.layer4(x)      # 14 -> 7

        # Classification
        x = self.avgpool(x)     # 7 -> 1
        x = torch.flatten(x, 1)
        x = self.fc(x)
        return x
```

### Receptive Field Calculation

The **receptive field** is the region of the input image that influences a particular neuron's output. Understanding receptive field growth is essential because a neuron can only make decisions based on information within its receptive field.

```python
def compute_receptive_field(architecture: list[dict]) -> list[dict]:
    # Computes receptive field size at each layer
    # Each layer dict: {"name": str, "kernel": int, "stride": int, "padding": int}
    # Returns list of dicts with added "receptive_field" and "jump" keys
    #
    # Formula: r_k = r_{k-1} + (kernel_k - 1) * j_{k-1}
    #          j_k = j_{k-1} * stride_k
    # where r = receptive field size, j = jump (stride product)

    results = []
    r = 1   # Initial receptive field (single pixel)
    j = 1   # Initial jump

    for layer in architecture:
        k = layer["kernel"]
        s = layer["stride"]
        r = r + (k - 1) * j
        j = j * s
        results.append({
            **layer,
            "receptive_field": r,
            "jump": j,
        })

    return results


# ResNet-18 receptive field calculation
resnet18_layers = [
    {"name": "conv1_7x7",     "kernel": 7, "stride": 2, "padding": 3},
    {"name": "maxpool_3x3",   "kernel": 3, "stride": 2, "padding": 1},
    {"name": "layer1_conv1",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer1_conv2",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer1_conv3",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer1_conv4",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer2_conv1",  "kernel": 3, "stride": 2, "padding": 1},
    {"name": "layer2_conv2",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer3_conv1",  "kernel": 3, "stride": 2, "padding": 1},
    {"name": "layer3_conv2",  "kernel": 3, "stride": 1, "padding": 1},
    {"name": "layer4_conv1",  "kernel": 3, "stride": 2, "padding": 1},
    {"name": "layer4_conv2",  "kernel": 3, "stride": 1, "padding": 1},
]

rf_results = compute_receptive_field(resnet18_layers)
# Final receptive field of ResNet-18: 435 pixels
# This means each neuron in the last conv layer "sees" a 435x435 region
```

### Parameter Counting

```python
def count_parameters(model: nn.Module, verbose: bool = True) -> int:
    # Count total and per-layer parameters in a PyTorch model
    # Distinguishes trainable vs frozen parameters
    total = 0
    trainable = 0
    layer_counts: dict[str, int] = {}

    for name, param in model.named_parameters():
        count = param.numel()
        total += count
        if param.requires_grad:
            trainable += count
        # Group by top-level module
        top_level = name.split(".")[0]
        layer_counts[top_level] = layer_counts.get(top_level, 0) + count

    if verbose:
        print(f"Total parameters:     {total:>12,}")
        print(f"Trainable parameters: {trainable:>12,}")
        print(f"\nPer-layer breakdown:")
        for name, count in layer_counts.items():
            pct = 100.0 * count / total
            print(f"  {name:<20s}: {count:>10,} ({pct:5.1f}%)")

    return total


# ResNet-18: ~11.7M parameters
# ResNet-50: ~25.6M parameters (uses bottleneck blocks)
# ResNet-152: ~60.2M parameters
model = ResNet18(num_classes=1000)
count_parameters(model)
```

## EfficientNet: Compound Scaling

EfficientNet introduced the insight that network **width** (channels), **depth** (layers), and **resolution** (input size) should be scaled together using a compound coefficient. Scaling only one dimension yields diminishing returns; however, scaling all three proportionally via the compound coefficient `phi` produces consistent gains.

The scaling rules are: depth = `alpha^phi`, width = `beta^phi`, resolution = `gamma^phi`, subject to `alpha * beta^2 * gamma^2 ≈ 2` (to approximately double FLOPs per step). The **trade-off** is that finding the optimal `alpha, beta, gamma` requires a neural architecture search on a small base model (EfficientNet-B0), then scaling up.

## ConvNeXt: Modernizing CNNs

ConvNeXt demonstrated that with modern training recipes and architectural tweaks borrowed from Transformers, pure ConvNets can match Vision Transformer performance. Key changes include: (1) using depthwise separable convolutions with large 7x7 kernels, (2) replacing ReLU with GELU activation, (3) replacing BatchNorm with LayerNorm, and (4) using an inverted bottleneck (wide -> narrow -> wide) instead of the traditional bottleneck. The **pitfall** is that ConvNeXt requires aggressive data augmentation and regularization techniques originally developed for ViT — without these, performance drops significantly.

## Summary and Key Takeaways

- **Skip connections** solve the degradation problem by providing gradient highways, enabling networks with 100+ layers to train effectively.
- **Residual learning** reframes the optimization target from learning `H(x)` to learning `F(x) = H(x) - x`, which is easier to optimize because the identity mapping is a good default.
- **Receptive field** grows linearly with depth but multiplicatively with stride — therefore, strided convolutions and pooling are essential for capturing global context.
- **Compound scaling** (EfficientNet) outperforms single-dimension scaling because width, depth, and resolution interact synergistically.
- **ConvNeXt** proves that the CNN vs Transformer debate is largely about training recipes, not fundamental architecture — best practice is to evaluate both for your specific task and data budget.
- **Parameter counting** reveals that the fully connected head often dominates parameter count in shallow networks, while convolutions dominate in deep networks.
"""
    ),
    (
        "cv/object-detection-yolo-internals",
        "Explain the YOLO family of object detection models in depth covering anchor-based vs anchor-free detection, non-maximum suppression, feature pyramid networks, and implement a YOLOv3 detection head in PyTorch with anchor box regression, objectness scoring, class prediction, IoU variants including GIoU DIoU and CIoU, and mAP calculation methodology.",
        r"""# Object Detection with YOLO: Internals and Implementation

## How Object Detection Works

Object detection combines two tasks: **localization** (where is the object?) and **classification** (what is the object?). Unlike image classification which produces a single label, detection must output a variable number of bounding boxes with associated class probabilities. This fundamental difference drives all the architectural complexity in detection systems.

**The core challenge** is that the number of objects varies per image, so the model cannot simply output a fixed-size vector. Two-stage detectors (R-CNN family) solve this by first proposing candidate regions, then classifying each. Single-stage detectors like YOLO solve this by dividing the image into a grid and predicting boxes directly from grid cells, which is dramatically faster but historically less accurate.

## Anchor-Based vs Anchor-Free Detection

### Anchor-Based (YOLOv2, v3, v5)

Anchor-based detectors use **predefined bounding box templates** (anchors) with specific aspect ratios and sizes. The network predicts **offsets** from these anchors rather than absolute coordinates. This simplifies learning because most objects cluster around a few common aspect ratios — however, the **trade-off** is that anchor design becomes a hyperparameter that requires dataset-specific tuning via k-means clustering.

**Common mistake**: Using anchors from COCO when training on a domain-specific dataset (e.g., satellite imagery, medical images). Always recompute anchors for your specific data distribution.

### Anchor-Free (FCOS, CenterNet, YOLOv8)

Anchor-free detectors predict objects as **center points** plus distances to the four bounding box edges. This eliminates the anchor hyperparameter entirely, reducing design complexity. The **pitfall** is that anchor-free detectors require careful handling of overlapping objects whose centers fall in the same grid cell — solutions include using Feature Pyramid Networks to assign objects to different scales.

## Feature Pyramid Networks (FPN)

Small objects need high-resolution feature maps with fine spatial detail, while large objects need low-resolution feature maps with rich semantic information. FPN solves this by building a **top-down pathway** with lateral connections that fuses features at multiple scales. Therefore, each scale of the pyramid can detect objects of the corresponding size effectively.

In YOLOv3, detection happens at three scales: stride 32 (large objects), stride 16 (medium), and stride 8 (small). Each scale uses different anchor sizes, and the feature maps are connected via upsampling and concatenation.

## YOLOv3 Detection Head Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, List
import math


class ConvBnRelu(nn.Module):
    # Standard conv -> batch norm -> leaky relu block used throughout YOLO
    def __init__(self, in_ch: int, out_ch: int, kernel: int = 3, stride: int = 1) -> None:
        super().__init__()
        padding = (kernel - 1) // 2
        self.conv = nn.Conv2d(in_ch, out_ch, kernel, stride, padding, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.act = nn.LeakyReLU(0.1, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.bn(self.conv(x)))


class YOLOv3DetectionHead(nn.Module):
    # YOLOv3 detection head for a single scale
    # For each grid cell and each anchor, predicts:
    #   - 4 bounding box offsets (tx, ty, tw, th)
    #   - 1 objectness score (is there an object?)
    #   - num_classes class probabilities
    # Total outputs per anchor: 5 + num_classes

    def __init__(
        self,
        in_channels: int,
        num_anchors: int = 3,
        num_classes: int = 80,
    ) -> None:
        super().__init__()
        self.num_anchors = num_anchors
        self.num_classes = num_classes
        self.num_outputs = 5 + num_classes  # tx, ty, tw, th, obj, classes

        # Detection block: 5 conv layers + 1 prediction conv
        mid_ch = in_channels // 2
        self.block = nn.Sequential(
            ConvBnRelu(in_channels, mid_ch, kernel=1),
            ConvBnRelu(mid_ch, in_channels, kernel=3),
            ConvBnRelu(in_channels, mid_ch, kernel=1),
            ConvBnRelu(mid_ch, in_channels, kernel=3),
            ConvBnRelu(in_channels, mid_ch, kernel=1),
        )

        # Feature map for upsampling to next scale
        self.feature_conv = ConvBnRelu(mid_ch, in_channels, kernel=3)

        # Final 1x1 conv to produce predictions
        self.pred_conv = nn.Conv2d(
            mid_ch, num_anchors * self.num_outputs, kernel_size=1, bias=True
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Returns (predictions, feature_map_for_next_scale)
        features = self.block(x)
        route = self.feature_conv(features)

        # Raw predictions: (batch, num_anchors * num_outputs, H, W)
        raw = self.pred_conv(features)

        batch_size, _, grid_h, grid_w = raw.shape
        # Reshape to (batch, num_anchors, num_outputs, H, W)
        raw = raw.view(batch_size, self.num_anchors, self.num_outputs, grid_h, grid_w)
        # Permute to (batch, num_anchors, H, W, num_outputs)
        raw = raw.permute(0, 1, 3, 4, 2).contiguous()

        return raw, route


def decode_yolo_predictions(
    raw: torch.Tensor,
    anchors: torch.Tensor,
    stride: int,
    num_classes: int,
) -> torch.Tensor:
    # Decode raw YOLO predictions to absolute bounding boxes
    # raw shape: (batch, num_anchors, grid_h, grid_w, 5 + num_classes)
    # anchors shape: (num_anchors, 2) — width, height in pixels
    # Returns: (batch, num_anchors * grid_h * grid_w, 5 + num_classes)
    #   where boxes are (cx, cy, w, h, obj, class1, class2, ...)

    batch, num_anchors, grid_h, grid_w, _ = raw.shape
    device = raw.device

    # Create grid offsets for cx, cy calculation
    grid_y, grid_x = torch.meshgrid(
        torch.arange(grid_h, device=device, dtype=torch.float32),
        torch.arange(grid_w, device=device, dtype=torch.float32),
        indexing="ij",
    )
    # Shape: (1, 1, grid_h, grid_w)
    grid_x = grid_x.unsqueeze(0).unsqueeze(0)
    grid_y = grid_y.unsqueeze(0).unsqueeze(0)

    # Decode bounding box center: sigmoid(tx) + grid_offset, scaled by stride
    cx = (torch.sigmoid(raw[..., 0]) + grid_x) * stride
    cy = (torch.sigmoid(raw[..., 1]) + grid_y) * stride

    # Decode width/height: anchor * exp(tw/th)
    # anchors reshaped to (1, num_anchors, 1, 1)
    anchor_w = anchors[:, 0].view(1, num_anchors, 1, 1)
    anchor_h = anchors[:, 1].view(1, num_anchors, 1, 1)
    w = anchor_w * torch.exp(raw[..., 2])
    h = anchor_h * torch.exp(raw[..., 3])

    # Objectness and class probabilities via sigmoid
    obj = torch.sigmoid(raw[..., 4])
    classes = torch.sigmoid(raw[..., 5:])

    # Stack and flatten spatial dimensions
    boxes = torch.stack([cx, cy, w, h, obj], dim=-1)
    output = torch.cat([boxes, classes], dim=-1)
    return output.view(batch, -1, 5 + num_classes)
```

## IoU Variants: GIoU, DIoU, CIoU

Standard **Intersection over Union** (IoU) fails as a loss function when boxes do not overlap, because the gradient is zero. This motivated several improvements, each addressing a specific limitation.

```python
import torch
from typing import Tuple


def bbox_iou_variants(
    pred: torch.Tensor,
    target: torch.Tensor,
    mode: str = "ciou",
) -> torch.Tensor:
    # Compute IoU variants between predicted and target boxes
    # Both tensors: (..., 4) in (cx, cy, w, h) format
    # Returns: IoU values with same batch dimensions

    # Convert center format to corner format
    pred_x1 = pred[..., 0] - pred[..., 2] / 2
    pred_y1 = pred[..., 1] - pred[..., 3] / 2
    pred_x2 = pred[..., 0] + pred[..., 2] / 2
    pred_y2 = pred[..., 1] + pred[..., 3] / 2

    target_x1 = target[..., 0] - target[..., 2] / 2
    target_y1 = target[..., 1] - target[..., 3] / 2
    target_x2 = target[..., 0] + target[..., 2] / 2
    target_y2 = target[..., 1] + target[..., 3] / 2

    # Intersection
    inter_x1 = torch.max(pred_x1, target_x1)
    inter_y1 = torch.max(pred_y1, target_y1)
    inter_x2 = torch.min(pred_x2, target_x2)
    inter_y2 = torch.min(pred_y2, target_y2)
    inter_area = torch.clamp(inter_x2 - inter_x1, min=0) * torch.clamp(inter_y2 - inter_y1, min=0)

    # Union
    pred_area = pred[..., 2] * pred[..., 3]
    target_area = target[..., 2] * target[..., 3]
    union_area = pred_area + target_area - inter_area + 1e-7

    iou = inter_area / union_area

    if mode == "iou":
        return iou

    # Smallest enclosing box
    enclose_x1 = torch.min(pred_x1, target_x1)
    enclose_y1 = torch.min(pred_y1, target_y1)
    enclose_x2 = torch.max(pred_x2, target_x2)
    enclose_y2 = torch.max(pred_y2, target_y2)

    if mode == "giou":
        # GIoU: penalizes the area of the enclosing box not covered by union
        enclose_area = (enclose_x2 - enclose_x1) * (enclose_y2 - enclose_y1) + 1e-7
        return iou - (enclose_area - union_area) / enclose_area

    # Diagonal distance of enclosing box (for DIoU and CIoU)
    c_diag_sq = (enclose_x2 - enclose_x1) ** 2 + (enclose_y2 - enclose_y1) ** 2 + 1e-7
    # Center distance squared
    center_dist_sq = (pred[..., 0] - target[..., 0]) ** 2 + (pred[..., 1] - target[..., 1]) ** 2

    if mode == "diou":
        # DIoU: penalizes center distance normalized by enclosing diagonal
        return iou - center_dist_sq / c_diag_sq

    if mode == "ciou":
        # CIoU: adds aspect ratio consistency penalty
        v = (4 / (math.pi ** 2)) * (
            torch.atan(target[..., 2] / (target[..., 3] + 1e-7))
            - torch.atan(pred[..., 2] / (pred[..., 3] + 1e-7))
        ) ** 2
        with torch.no_grad():
            alpha = v / (1 - iou + v + 1e-7)
        return iou - center_dist_sq / c_diag_sq - alpha * v

    raise ValueError(f"Unknown mode: {mode}")
```

## Non-Maximum Suppression (NMS)

After detection, the model outputs thousands of candidate boxes. NMS filters these to keep only the best predictions by removing overlapping boxes. The **trade-off** is the IoU threshold: too low (0.3) suppresses valid nearby objects, too high (0.7) allows duplicate detections. **Best practice** is to use **Soft-NMS**, which decays confidence scores of overlapping boxes instead of hard removal, because it handles occluded objects more gracefully.

## mAP Calculation

**Mean Average Precision** (mAP) is the standard detection metric. For each class, predictions are ranked by confidence, and precision-recall pairs are computed at each threshold. The **Average Precision** (AP) is the area under the precision-recall curve (using 101-point interpolation in COCO). mAP is then the mean AP across all classes. COCO mAP averages over IoU thresholds from 0.5 to 0.95 in steps of 0.05, which is stricter than Pascal VOC's single 0.5 threshold.

**Pitfall**: A high mAP@0.5 but low mAP@0.75 indicates that your model finds objects but localizes them poorly. This usually means the regression head needs more capacity or the IoU loss function needs improvement (switch from L1 to CIoU).

## Summary and Key Takeaways

- **YOLO's core idea** is treating detection as regression: divide the image into a grid and predict boxes directly, achieving real-time inference speeds of 30-150+ FPS depending on model variant.
- **Anchor boxes** provide a strong prior on object shapes, making box regression easier to learn; however, they introduce hyperparameters that must be tuned per dataset. Anchor-free approaches eliminate this at the cost of needing more sophisticated assignment strategies.
- **Feature Pyramid Networks** are essential for multi-scale detection because small objects are only visible in early, high-resolution feature maps while large objects require deep, semantically rich features.
- **CIoU loss** is the best practice for bounding box regression because it simultaneously optimizes overlap, center distance, and aspect ratio consistency — therefore converging faster and to better solutions than L1 or smooth-L1 losses.
- **NMS** is a necessary post-processing step that trades off between suppressing duplicates and preserving nearby objects; Soft-NMS provides a less aggressive alternative.
- **mAP** evaluation must match the target benchmark (COCO vs VOC) because the IoU threshold averaging dramatically affects reported numbers.
"""
    ),
    (
        "cv/image-segmentation-unet",
        "Explain image segmentation approaches including semantic, instance, and panoptic segmentation, and implement a complete U-Net architecture in PyTorch with encoder-decoder skip connections, transpose convolutions, Dice loss, focal loss for class imbalance, and cover DeepLab atrous spatial pyramid pooling for multi-scale context aggregation.",
        r"""# Image Segmentation: From Pixels to Semantic Understanding

## What is Image Segmentation?

Image segmentation assigns a label to **every pixel** in an image, producing a dense prediction map rather than a single class label or bounding box. This pixel-level understanding is critical for applications like autonomous driving, medical imaging, satellite analysis, and augmented reality. Three variants exist, each with increasing complexity.

### Semantic Segmentation

Assigns a class label to every pixel without distinguishing between different instances of the same class. For example, all cars are labeled "car" regardless of how many exist. **Best practice**: use semantic segmentation when you care about "what is where" but not "how many."

### Instance Segmentation

Identifies each individual object instance with a unique mask. Two cars get two separate masks. This is harder because the model must both classify and distinguish instances. Mask R-CNN is the classic approach, combining Faster R-CNN detection with a parallel mask prediction branch.

### Panoptic Segmentation

Unifies semantic and instance segmentation: every pixel gets both a class label and an instance ID. "Stuff" classes (sky, road, grass) get semantic labels only, while "thing" classes (car, person, dog) get both class and instance labels. Therefore, panoptic segmentation provides the most complete scene understanding.

## U-Net Architecture

U-Net was originally designed for biomedical image segmentation where training data is scarce. Its key innovation is the **symmetric encoder-decoder architecture with skip connections** that concatenate high-resolution features from the encoder directly to the decoder. This solves the fundamental **trade-off** in segmentation: deep features capture semantics but lose spatial detail, while shallow features preserve spatial detail but lack semantic understanding.

**Common mistake**: Confusing U-Net skip connections with ResNet skip connections. ResNet uses **additive** shortcuts within a block for gradient flow. U-Net uses **concatenation** across the encoder-decoder boundary for feature fusion. They solve completely different problems.

### Full U-Net Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional, Tuple


class DoubleConv(nn.Module):
    # Two consecutive (conv3x3 -> BN -> ReLU) blocks
    # This is the fundamental building block of U-Net

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class EncoderBlock(nn.Module):
    # Encoder: MaxPool -> DoubleConv
    # Halves spatial dimensions, increases channel depth

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(self.pool(x))


class DecoderBlock(nn.Module):
    # Decoder: Upsample -> Concatenate skip -> DoubleConv
    # Doubles spatial dimensions, decreases channel depth
    # Uses transpose convolution (learned upsampling)

    def __init__(self, in_channels: int, out_channels: int, bilinear: bool = False) -> None:
        super().__init__()
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels)
        else:
            # Transpose convolution: learnable upsampling
            # Halves channels while doubling spatial dimensions
            self.up = nn.ConvTranspose2d(
                in_channels, in_channels // 2,
                kernel_size=2, stride=2
            )
            self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = self.up(x)

        # Handle size mismatch from odd-sized inputs
        # This is a common pitfall when input dimensions are not powers of 2
        diff_h = skip.shape[2] - x.shape[2]
        diff_w = skip.shape[3] - x.shape[3]
        x = F.pad(x, [diff_w // 2, diff_w - diff_w // 2,
                       diff_h // 2, diff_h - diff_h // 2])

        # Concatenate along channel dimension (NOT addition)
        x = torch.cat([skip, x], dim=1)
        return self.conv(x)


class UNet(nn.Module):
    # Full U-Net for semantic segmentation
    # Encoder: 4 downsampling stages (64->128->256->512->1024 channels)
    # Decoder: 4 upsampling stages with skip connections
    # Output: per-pixel class logits

    def __init__(
        self,
        in_channels: int = 3,
        num_classes: int = 21,
        base_features: int = 64,
        bilinear: bool = False,
    ) -> None:
        super().__init__()
        f = base_features

        # Encoder path (contracting)
        self.enc0 = DoubleConv(in_channels, f)        # 3 -> 64
        self.enc1 = EncoderBlock(f, f * 2)             # 64 -> 128
        self.enc2 = EncoderBlock(f * 2, f * 4)         # 128 -> 256
        self.enc3 = EncoderBlock(f * 4, f * 8)         # 256 -> 512

        # Bottleneck
        self.bottleneck = EncoderBlock(f * 8, f * 16)  # 512 -> 1024

        # Decoder path (expanding) with skip connections
        self.dec3 = DecoderBlock(f * 16, f * 8, bilinear)  # 1024+512 -> 512
        self.dec2 = DecoderBlock(f * 8, f * 4, bilinear)   # 512+256 -> 256
        self.dec1 = DecoderBlock(f * 4, f * 2, bilinear)   # 256+128 -> 128
        self.dec0 = DecoderBlock(f * 2, f, bilinear)       # 128+64 -> 64

        # Final 1x1 convolution for pixel-wise classification
        self.final_conv = nn.Conv2d(f, num_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Encoder — save skip connections
        s0 = self.enc0(x)
        s1 = self.enc1(s0)
        s2 = self.enc2(s1)
        s3 = self.enc3(s2)

        # Bottleneck
        b = self.bottleneck(s3)

        # Decoder — concatenate skip connections
        d3 = self.dec3(b, s3)
        d2 = self.dec2(d3, s2)
        d1 = self.dec1(d2, s1)
        d0 = self.dec0(d1, s0)

        return self.final_conv(d0)
```

## Loss Functions for Segmentation

### Dice Loss

Cross-entropy loss treats each pixel independently, which works poorly with class imbalance (e.g., a tumor occupying 1% of pixels). **Dice loss** directly optimizes the Dice coefficient (F1 score) between predicted and ground truth masks, making it robust to imbalanced datasets.

### Focal Loss

Focal loss down-weights the loss contribution from easy, well-classified pixels, forcing the model to focus on hard examples. This is essential when the background class dominates (99%+ of pixels in some medical imaging tasks).

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceLoss(nn.Module):
    # Dice loss for segmentation — directly optimizes overlap
    # Handles multi-class by computing per-class dice and averaging
    # smooth factor prevents division by zero and stabilizes gradients

    def __init__(self, smooth: float = 1.0, ignore_index: int = -1) -> None:
        super().__init__()
        self.smooth = smooth
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # logits: (B, C, H, W) — raw predictions
        # targets: (B, H, W) — integer class labels
        num_classes = logits.shape[1]
        probs = F.softmax(logits, dim=1)  # (B, C, H, W)

        # Create valid mask to ignore unlabeled pixels
        valid_mask = (targets != self.ignore_index).unsqueeze(1)  # (B, 1, H, W)

        # One-hot encode targets: (B, H, W) -> (B, C, H, W)
        targets_clamped = targets.clamp(min=0)  # Avoid negative indexing
        one_hot = F.one_hot(targets_clamped, num_classes)  # (B, H, W, C)
        one_hot = one_hot.permute(0, 3, 1, 2).float()     # (B, C, H, W)

        # Apply valid mask
        probs = probs * valid_mask
        one_hot = one_hot * valid_mask

        # Per-class Dice coefficient
        dims = (0, 2, 3)  # Sum over batch and spatial dims, keep classes
        intersection = (probs * one_hot).sum(dim=dims)
        cardinality = probs.sum(dim=dims) + one_hot.sum(dim=dims)

        dice = (2.0 * intersection + self.smooth) / (cardinality + self.smooth)
        return 1.0 - dice.mean()


class FocalLoss(nn.Module):
    # Focal loss: CE * (1 - p_t)^gamma
    # gamma=0 recovers standard cross-entropy
    # gamma=2 is the recommended default (from the original paper)
    # alpha provides per-class weighting for additional imbalance handling

    def __init__(
        self,
        gamma: float = 2.0,
        alpha: Optional[torch.Tensor] = None,
        ignore_index: int = -1,
    ) -> None:
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # logits: (B, C, H, W), targets: (B, H, W)
        ce = F.cross_entropy(
            logits, targets, reduction="none", ignore_index=self.ignore_index
        )
        # p_t: probability of the true class
        p_t = torch.exp(-ce)
        focal_weight = (1.0 - p_t) ** self.gamma

        loss = focal_weight * ce

        if self.alpha is not None:
            # Gather per-pixel alpha weights
            alpha_t = self.alpha.to(logits.device)[targets.clamp(min=0)]
            valid = targets != self.ignore_index
            loss = loss * alpha_t * valid.float()

        return loss.mean()


class CombinedSegmentationLoss(nn.Module):
    # Best practice: combine Dice + Focal for robust segmentation training
    # Dice handles class imbalance; Focal handles hard examples
    # The trade-off is controlled by the mixing weight lambda_dice

    def __init__(self, lambda_dice: float = 0.5, gamma: float = 2.0) -> None:
        super().__init__()
        self.dice = DiceLoss()
        self.focal = FocalLoss(gamma=gamma)
        self.lambda_dice = lambda_dice

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return self.lambda_dice * self.dice(logits, targets) + (1 - self.lambda_dice) * self.focal(logits, targets)
```

## DeepLab: Atrous Spatial Pyramid Pooling

DeepLab addresses multi-scale context by using **atrous (dilated) convolutions** at multiple rates in parallel. Standard convolutions with larger kernels increase receptive field but also increase parameters quadratically. Atrous convolutions increase receptive field **without** increasing parameters, because they insert gaps ("holes") between kernel elements.

**ASPP** applies four parallel atrous convolutions with different dilation rates (e.g., 6, 12, 18) plus a global average pooling branch. The outputs are concatenated and fused with a 1x1 convolution. This captures context at multiple scales simultaneously — a street scene may have a person (small), a car (medium), and a building (large) in the same image, and ASPP's multi-rate design handles all three effectively.

**Pitfall**: Using very large dilation rates (e.g., 24+) on small feature maps causes the kernel to sample outside the feature map boundaries, degenerating to a 1x1 convolution. Therefore, dilation rates must be chosen relative to the feature map size.

## Summary and Key Takeaways

- **Semantic segmentation** classifies every pixel but does not distinguish instances; **instance segmentation** separates individual objects; **panoptic segmentation** unifies both into a complete scene understanding.
- **U-Net's skip connections** concatenate encoder features to decoder features, preserving spatial detail that would otherwise be lost during downsampling — this is the architectural key to precise boundary delineation.
- **Dice loss** directly optimizes the overlap metric and is robust to class imbalance because it normalizes by the total area of both prediction and ground truth. **Best practice** is to combine Dice with Focal loss.
- **Focal loss** down-weights easy examples by a factor of `(1 - p_t)^gamma`, forcing the model to focus on hard, misclassified pixels near object boundaries.
- **Atrous convolutions** in DeepLab expand receptive field without increasing parameters, however they must be sized appropriately relative to feature map dimensions to avoid degenerate behavior.
- **Transpose convolutions** are learnable upsampling operations that are preferred over bilinear interpolation when the model has sufficient training data because they can learn task-specific upsampling patterns.
"""
    ),
    (
        "cv/vision-transformers-vit",
        "Explain Vision Transformers in depth including patch embedding, position encoding, CLS token classification, DeiT knowledge distillation, and Swin Transformer shifted windows, and implement a complete ViT from scratch in PyTorch with patch embedding layer, multi-head self-attention, transformer encoder blocks, classification head, and cover data augmentation strategies like CutMix, MixUp, and RandAugment.",
        r"""# Vision Transformers: Applying Self-Attention to Images

## Why Transformers for Vision?

Convolutional neural networks impose a strong **inductive bias**: locality (nearby pixels are processed together) and translation equivariance (the same filter detects features everywhere). These biases help CNNs learn efficiently from limited data, however they also limit the model's ability to capture **long-range dependencies**. A pixel in the top-left corner cannot directly attend to a pixel in the bottom-right corner without stacking many convolutional layers.

Vision Transformers (ViT) remove these biases entirely by treating an image as a sequence of patches and processing them with standard Transformer self-attention. Each patch can attend to every other patch in a single layer, enabling **global receptive field from the first layer**. The **trade-off** is that without inductive biases, ViT requires significantly more training data — the original ViT paper needed JFT-300M (300 million images) to outperform CNNs trained on ImageNet alone.

## ViT Architecture Components

### Patch Embedding

The image is divided into non-overlapping patches (typically 16x16 pixels), and each patch is linearly projected to a **D-dimensional embedding vector**. A 224x224 image becomes a sequence of 196 patches (14x14 grid), each represented as a vector. This is mathematically equivalent to a single convolution with kernel size and stride both equal to the patch size.

### Position Encoding

Because self-attention is permutation-invariant, the model has no notion of spatial arrangement without explicit position information. ViT uses **learnable 1D position embeddings** — a trainable vector added to each patch embedding. Surprisingly, learned 1D positions outperform handcrafted 2D sinusoidal encodings in practice, because the model learns to encode 2D spatial relationships in the 1D position vectors during training.

### CLS Token

Following BERT, ViT prepends a special **[CLS] token** to the sequence. After processing through the Transformer encoder, the CLS token's output serves as the aggregate image representation for classification. This avoids the need for global average pooling and allows the model to learn what information to aggregate.

**Common mistake**: Assuming the CLS token is essential. In practice, **global average pooling** over all patch tokens performs equally well and is simpler. Many modern ViT variants (DeiT, Swin) support both approaches.

### Complete ViT Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional
import math


class PatchEmbedding(nn.Module):
    # Convert image to sequence of patch embeddings
    # Equivalent to splitting into patches and linear projection
    # Implemented efficiently as a single strided convolution

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        in_channels: int = 3,
        embed_dim: int = 768,
    ) -> None:
        super().__init__()
        self.img_size = img_size
        self.patch_size = patch_size
        self.num_patches = (img_size // patch_size) ** 2
        # Single conv with kernel_size=stride=patch_size
        # This extracts and projects patches in one operation
        self.projection = nn.Conv2d(
            in_channels, embed_dim,
            kernel_size=patch_size, stride=patch_size
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, H, W) -> (B, num_patches, embed_dim)
        x = self.projection(x)  # (B, embed_dim, H/P, W/P)
        x = x.flatten(2)        # (B, embed_dim, num_patches)
        x = x.transpose(1, 2)   # (B, num_patches, embed_dim)
        return x


class MultiHeadSelfAttention(nn.Module):
    # Standard multi-head self-attention with optional attention dropout
    # Q, K, V are projected from the same input (self-attention)

    def __init__(
        self,
        embed_dim: int = 768,
        num_heads: int = 12,
        attn_drop: float = 0.0,
        proj_drop: float = 0.0,
    ) -> None:
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.scale = self.head_dim ** -0.5

        # Combined QKV projection for efficiency
        self.qkv = nn.Linear(embed_dim, embed_dim * 3)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(embed_dim, embed_dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, N, D = x.shape
        # Project to Q, K, V and reshape for multi-head
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, self.head_dim)
        qkv = qkv.permute(2, 0, 3, 1, 4)  # (3, B, heads, N, head_dim)
        q, k, v = qkv.unbind(0)

        # Scaled dot-product attention
        attn = (q @ k.transpose(-2, -1)) * self.scale  # (B, heads, N, N)
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        # Aggregate values
        out = (attn @ v).transpose(1, 2).reshape(B, N, D)
        out = self.proj(out)
        out = self.proj_drop(out)
        return out


class TransformerBlock(nn.Module):
    # Standard Transformer encoder block
    # Pre-norm architecture (LayerNorm before attention/MLP)
    # because pre-norm is more stable during training than post-norm

    def __init__(
        self,
        embed_dim: int = 768,
        num_heads: int = 12,
        mlp_ratio: float = 4.0,
        drop: float = 0.0,
        attn_drop: float = 0.0,
    ) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(embed_dim)
        self.attn = MultiHeadSelfAttention(embed_dim, num_heads, attn_drop, drop)
        self.norm2 = nn.LayerNorm(embed_dim)

        mlp_hidden = int(embed_dim * mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim, mlp_hidden),
            nn.GELU(),
            nn.Dropout(drop),
            nn.Linear(mlp_hidden, embed_dim),
            nn.Dropout(drop),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pre-norm residual connections
        x = x + self.attn(self.norm1(x))
        x = x + self.mlp(self.norm2(x))
        return x


class VisionTransformer(nn.Module):
    # Complete Vision Transformer (ViT) for image classification
    # Architecture: patch_embed -> [CLS] + pos_embed -> N x transformer blocks -> head
    #
    # ViT-Base: embed_dim=768, depth=12, heads=12 (86M params)
    # ViT-Large: embed_dim=1024, depth=24, heads=16 (307M params)
    # ViT-Huge: embed_dim=1280, depth=32, heads=16 (632M params)

    def __init__(
        self,
        img_size: int = 224,
        patch_size: int = 16,
        in_channels: int = 3,
        num_classes: int = 1000,
        embed_dim: int = 768,
        depth: int = 12,
        num_heads: int = 12,
        mlp_ratio: float = 4.0,
        drop_rate: float = 0.0,
        attn_drop_rate: float = 0.0,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.embed_dim = embed_dim

        # Patch embedding
        self.patch_embed = PatchEmbedding(img_size, patch_size, in_channels, embed_dim)
        num_patches = self.patch_embed.num_patches

        # CLS token and position embeddings (learnable)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches + 1, embed_dim))
        self.pos_drop = nn.Dropout(drop_rate)

        # Transformer encoder
        self.blocks = nn.Sequential(*[
            TransformerBlock(embed_dim, num_heads, mlp_ratio, drop_rate, attn_drop_rate)
            for _ in range(depth)
        ])

        # Classification head
        self.norm = nn.LayerNorm(embed_dim)
        self.head = nn.Linear(embed_dim, num_classes)

        # Weight initialization
        nn.init.trunc_normal_(self.pos_embed, std=0.02)
        nn.init.trunc_normal_(self.cls_token, std=0.02)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.trunc_normal_(m.weight, std=0.02)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.LayerNorm):
            nn.init.ones_(m.weight)
            nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B = x.shape[0]

        # Patch embedding: (B, 3, 224, 224) -> (B, 196, 768)
        x = self.patch_embed(x)

        # Prepend CLS token: (B, 196, 768) -> (B, 197, 768)
        cls_tokens = self.cls_token.expand(B, -1, -1)
        x = torch.cat([cls_tokens, x], dim=1)

        # Add position embeddings
        x = x + self.pos_embed
        x = self.pos_drop(x)

        # Transformer encoder
        x = self.blocks(x)
        x = self.norm(x)

        # Classification from CLS token
        cls_output = x[:, 0]
        return self.head(cls_output)
```

## DeiT: Data-Efficient Image Transformers

DeiT (Data-efficient Image Transformers) demonstrated that ViT can match CNN performance when trained **only on ImageNet-1K** (1.28M images) — without the massive JFT-300M dataset. The key innovations are: (1) heavy data augmentation, (2) knowledge distillation from a CNN teacher, and (3) a **distillation token** that learns from the teacher's hard labels alongside the CLS token learning from ground truth.

**Best practice**: When training ViT on datasets smaller than ImageNet, always use DeiT-style training. The distillation from a strong CNN teacher (e.g., RegNet) provides the inductive biases that ViT lacks natively.

## Swin Transformer: Shifted Windows

Standard ViT has **quadratic complexity** O(N^2) in the number of patches because every patch attends to every other patch. For a 224x224 image with 16x16 patches, N=196 is manageable. However, for dense prediction tasks (segmentation, detection) requiring 4x higher resolution, N becomes prohibitively large.

Swin Transformer solves this by restricting self-attention to **local windows** (e.g., 7x7 patches), then **shifting** the window partition between consecutive layers to enable cross-window information flow. This reduces complexity to O(N) while maintaining global receptive field through the shifting mechanism. The **trade-off** is added implementation complexity from the shifted window masking.

## Data Augmentation Strategies

ViT's lack of inductive bias makes it heavily dependent on data augmentation. Three advanced strategies are essential.

```python
import torch
import torch.nn.functional as F
import numpy as np
from typing import Tuple


def cutmix(
    images: torch.Tensor,
    labels: torch.Tensor,
    alpha: float = 1.0,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    # CutMix: cut a random patch from one image and paste onto another
    # Labels are mixed proportionally to the area ratio
    # This forces the model to attend to multiple regions, not just the
    # most discriminative part — therefore improving robustness

    B, C, H, W = images.shape
    lam = np.random.beta(alpha, alpha)

    # Random bounding box
    cut_ratio = np.sqrt(1.0 - lam)
    cut_h = int(H * cut_ratio)
    cut_w = int(W * cut_ratio)
    cx = np.random.randint(H)
    cy = np.random.randint(W)

    x1 = np.clip(cx - cut_h // 2, 0, H)
    y1 = np.clip(cy - cut_w // 2, 0, W)
    x2 = np.clip(cx + cut_h // 2, 0, H)
    y2 = np.clip(cy + cut_w // 2, 0, W)

    # Shuffle indices for mixing
    indices = torch.randperm(B, device=images.device)

    # Apply CutMix
    mixed = images.clone()
    mixed[:, :, x1:x2, y1:y2] = images[indices, :, x1:x2, y1:y2]

    # Adjust lambda to exact area ratio
    lam = 1.0 - (x2 - x1) * (y2 - y1) / (H * W)
    return mixed, labels, labels[indices], lam


def mixup(
    images: torch.Tensor,
    labels: torch.Tensor,
    alpha: float = 0.2,
    num_classes: int = 1000,
) -> Tuple[torch.Tensor, torch.Tensor]:
    # MixUp: linearly interpolate pairs of images and their labels
    # Produces convex combinations: x_mix = lam*x_i + (1-lam)*x_j
    # Smooths decision boundaries and acts as a regularizer
    # Common mistake: applying MixUp with too high alpha (>1.0)
    # which creates unrecognizable images

    lam = np.random.beta(alpha, alpha)
    indices = torch.randperm(images.shape[0], device=images.device)

    mixed_images = lam * images + (1 - lam) * images[indices]

    # Convert to soft labels for cross-entropy
    one_hot = F.one_hot(labels, num_classes).float()
    one_hot_shuffled = F.one_hot(labels[indices], num_classes).float()
    mixed_labels = lam * one_hot + (1 - lam) * one_hot_shuffled

    return mixed_images, mixed_labels


def rand_augment(
    image: torch.Tensor,
    num_ops: int = 2,
    magnitude: int = 9,
) -> torch.Tensor:
    # RandAugment: apply N random augmentations at magnitude M
    # Simplifies augmentation search to just 2 hyperparameters
    # Best practice: start with num_ops=2, magnitude=9, then tune
    # Pitfall: high magnitude (>15) can create unrealistic images
    # that hurt rather than help generalization
    #
    # In production, use torchvision.transforms.RandAugment directly
    # This implementation shows the core idea for educational purposes

    from torchvision import transforms

    augment_pool = [
        transforms.RandomRotation(degrees=30 * magnitude / 10),
        transforms.RandomAffine(degrees=0, translate=(0.1 * magnitude / 10, 0.1 * magnitude / 10)),
        transforms.RandomAffine(degrees=0, shear=10 * magnitude / 10),
        transforms.ColorJitter(brightness=0.1 * magnitude / 10),
        transforms.ColorJitter(contrast=0.1 * magnitude / 10),
        transforms.ColorJitter(saturation=0.1 * magnitude / 10),
        transforms.RandomAutocontrast(p=1.0),
        transforms.RandomEqualize(p=1.0),
        transforms.RandomPosterize(bits=max(1, 8 - magnitude), p=1.0),
        transforms.RandomSolarize(threshold=256 - 25 * magnitude / 10, p=1.0),
    ]

    # Randomly select num_ops augmentations and apply sequentially
    chosen = np.random.choice(len(augment_pool), num_ops, replace=False)
    for idx in chosen:
        image = augment_pool[idx](image)

    return image
```

## Summary and Key Takeaways

- **ViT removes CNN inductive biases** (locality, translation equivariance), replacing them with a general-purpose self-attention mechanism that has global receptive field from the first layer; however, this requires substantially more training data or knowledge distillation.
- **Patch embedding** converts a 2D image into a 1D sequence by splitting into fixed-size patches and linearly projecting each — this is the bridge between vision and the Transformer architecture.
- **Learnable position embeddings** encode spatial arrangement; the CLS token aggregates global information for classification, though global average pooling is an equally effective alternative.
- **DeiT** makes ViT practical on ImageNet-scale data through aggressive augmentation and CNN-to-ViT knowledge distillation — **best practice** when your dataset is under 10M images.
- **Swin Transformer** reduces ViT's quadratic complexity to linear via windowed attention with cross-window shifting, therefore enabling Transformer-based dense prediction at high resolution.
- **CutMix, MixUp, and RandAugment** are essential for ViT training because without strong augmentation, ViT overfits severely on datasets smaller than JFT-300M. The **trade-off** is that too-aggressive augmentation creates unrealistic training samples that can hurt convergence.
"""
    ),
    (
        "cv/self-supervised-visual-learning",
        "Explain self-supervised visual representation learning in depth including contrastive methods like SimCLR, MoCo, and BYOL, masked image modeling approaches like MAE and BEiT, and DINO self-distillation, and implement a complete SimCLR training loop in PyTorch with projection head, NT-Xent contrastive loss, augmentation pipeline, and cover linear probing evaluation methodology and transfer learning benchmark protocols.",
        r"""# Self-Supervised Visual Representation Learning

## Why Self-Supervised Learning Matters

Labeled data is the bottleneck of supervised learning. ImageNet took years and millions of dollars to annotate. Medical imaging datasets are even more expensive because they require expert radiologists. Self-supervised learning (SSL) learns visual representations from **unlabeled images** by solving **pretext tasks** — tasks where the supervision signal comes from the data itself. The learned representations then transfer to downstream tasks via fine-tuning or linear probing.

**The core insight**: A model that learns to solve a well-designed pretext task must understand visual semantics to succeed. If a model can identify that two augmented views of the same image are related while distinguishing them from views of different images, it must have learned meaningful features like object shape, texture, color, and spatial arrangement.

Self-supervised methods now match or exceed supervised pretraining on many transfer learning benchmarks. This is a paradigm shift because it decouples representation quality from label availability.

## Contrastive Learning Methods

### SimCLR: Simple Framework for Contrastive Learning

SimCLR learns representations by maximizing agreement between two **augmented views** of the same image (positive pair) while pushing apart views from different images (negative pairs). The key components are: (1) a stochastic augmentation pipeline that generates diverse views, (2) a base encoder (ResNet) that extracts features, (3) a **projection head** (MLP) that maps features to a space where contrastive loss is applied, and (4) the **NT-Xent** (Normalized Temperature-scaled Cross-Entropy) loss.

**Common mistake**: Applying contrastive loss in the representation space directly. The projection head is critical — representations from the layer **before** the projection head transfer better to downstream tasks. Therefore, the projection head is discarded after pretraining.

### MoCo: Momentum Contrast

SimCLR requires very large batch sizes (4096+) to provide enough negative pairs. MoCo solves this with a **momentum-updated encoder** and a **queue** of negative features. The query encoder is updated by gradient descent, while the key encoder is updated as an exponential moving average of the query encoder: `key_encoder = m * key_encoder + (1-m) * query_encoder` with momentum `m = 0.999`. The queue stores key representations from recent mini-batches, providing a large pool of negatives without requiring large batches.

**Best practice**: Use MoCo when GPU memory is limited, because it achieves SimCLR-level performance with batch sizes as small as 256.

### BYOL: Bootstrap Your Own Latent

BYOL eliminates negative pairs entirely by using an asymmetric architecture: an **online network** (encoder + projector + predictor) learns to predict the output of a **target network** (encoder + projector), where the target is updated via momentum. Because the predictor exists only in the online network, the architecture is asymmetric, preventing **representational collapse** (where all images map to the same point).

The **trade-off** with BYOL is that it is sensitive to batch normalization statistics and training instability. Without careful implementation, the model can collapse silently — the loss decreases but representations become degenerate.

## Masked Image Modeling

### MAE: Masked Autoencoders

Inspired by BERT's masked language modeling, MAE randomly masks a large fraction (75%) of image patches and trains a ViT to reconstruct the missing pixels. The asymmetric encoder-decoder architecture processes only visible patches (25%) through a heavy encoder, then a lightweight decoder reconstructs the full image. This is computationally efficient because the encoder processes only a quarter of the patches.

### BEiT: BERT Pre-Training for Image Transformers

BEiT differs from MAE by predicting **discrete visual tokens** (from a pretrained DALL-E tokenizer) rather than raw pixels. This forces the model to learn semantic rather than pixel-level features, however it introduces a dependency on the visual tokenizer quality.

## DINO: Self-Distillation with No Labels

DINO trains a student network to match the output distribution of a teacher network (momentum-updated copy) across different augmented views. The teacher sees global crops (large) while the student sees both global and local crops (small). This encourages the student to learn semantic features from local regions — because a small crop of a dog's face should produce representations similar to the full dog image.

**Pitfall**: DINO's loss uses centering and sharpening to prevent collapse. Without proper centering of the teacher's output, all images collapse to a uniform distribution. This is a subtle failure mode that shows low loss but useless representations.

## SimCLR Implementation

```python
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms, models
from typing import Tuple, Optional
import math


class SimCLRAugmentation:
    # Stochastic augmentation pipeline for SimCLR
    # Creates two correlated views of the same image
    # The augmentations must be strong enough to force semantic learning
    # but not so strong that the task becomes impossible
    #
    # Critical augmentations (in order of importance):
    # 1. Random resized crop (spatial)
    # 2. Color jitter (appearance)
    # 3. Gaussian blur (texture)
    # 4. Horizontal flip (viewpoint)
    # Best practice: color jitter strength 0.8 and grayscale p=0.2

    def __init__(self, img_size: int = 224) -> None:
        self.transform = transforms.Compose([
            transforms.RandomResizedCrop(img_size, scale=(0.2, 1.0)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomApply([
                transforms.ColorJitter(
                    brightness=0.8, contrast=0.8,
                    saturation=0.8, hue=0.2
                )
            ], p=0.8),
            transforms.RandomGrayscale(p=0.2),
            transforms.RandomApply([
                transforms.GaussianBlur(kernel_size=23, sigma=(0.1, 2.0))
            ], p=0.5),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ])

    def __call__(self, image: "PIL.Image") -> Tuple[torch.Tensor, torch.Tensor]:
        # Return two independently augmented views
        return self.transform(image), self.transform(image)


class ProjectionHead(nn.Module):
    # Non-linear projection head: maps representations to contrastive space
    # 2-layer MLP with BN and ReLU (SimCLR v1) or 3-layer (SimCLR v2)
    # Output dimension is typically 128 (much smaller than representation)
    #
    # The projection head is DISCARDED after pretraining
    # because the layer before it transfers better

    def __init__(
        self,
        input_dim: int = 2048,
        hidden_dim: int = 2048,
        output_dim: int = 128,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class SimCLR(nn.Module):
    # Full SimCLR model: encoder + projection head
    # Encoder is typically ResNet-50 with the final FC layer removed
    # The encoder output (2048-d for ResNet-50) is the representation
    # The projection head output (128-d) is used only for contrastive loss

    def __init__(
        self,
        backbone: str = "resnet50",
        projection_dim: int = 128,
    ) -> None:
        super().__init__()

        # Load backbone and remove classification head
        encoder = getattr(models, backbone)(weights=None)
        self.repr_dim = encoder.fc.in_features
        encoder.fc = nn.Identity()
        self.encoder = encoder

        # Projection head
        self.projector = ProjectionHead(
            input_dim=self.repr_dim,
            hidden_dim=self.repr_dim,
            output_dim=projection_dim,
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Returns both representation (for downstream) and projection (for loss)
        h = self.encoder(x)       # Representation: (B, 2048)
        z = self.projector(h)     # Projection: (B, 128)
        return h, z


def nt_xent_loss(
    z_i: torch.Tensor,
    z_j: torch.Tensor,
    temperature: float = 0.5,
) -> torch.Tensor:
    # NT-Xent (Normalized Temperature-scaled Cross-Entropy) loss
    # For each positive pair (z_i, z_j), all other samples in the batch
    # serve as negatives. With batch size B, each sample has 1 positive
    # and 2(B-1) negatives.
    #
    # Temperature controls the sharpness of the distribution:
    # - Low temp (0.1): focuses on hard negatives, less stable
    # - High temp (1.0): treats all negatives equally, less discriminative
    # - Best practice: temperature = 0.5 (or tune on validation)

    B = z_i.shape[0]
    device = z_i.device

    # L2 normalize projections
    z_i = F.normalize(z_i, dim=1)
    z_j = F.normalize(z_j, dim=1)

    # Concatenate: [z_i_0, z_i_1, ..., z_j_0, z_j_1, ...]
    z = torch.cat([z_i, z_j], dim=0)  # (2B, D)

    # Full cosine similarity matrix: (2B, 2B)
    sim_matrix = torch.mm(z, z.t()) / temperature

    # Mask out self-similarity (diagonal)
    mask = torch.eye(2 * B, device=device, dtype=torch.bool)
    sim_matrix = sim_matrix.masked_fill(mask, -1e9)

    # Positive pairs: (i, i+B) and (i+B, i)
    # Labels: for row i, the positive is at column i+B
    # For row i+B, the positive is at column i
    labels = torch.cat([
        torch.arange(B, 2 * B, device=device),  # z_i -> z_j
        torch.arange(0, B, device=device),       # z_j -> z_i
    ])

    # Cross-entropy treats this as a 2B-way classification
    loss = F.cross_entropy(sim_matrix, labels)
    return loss
```

### Training Loop

```python
def train_simclr(
    model: SimCLR,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: Optional[torch.optim.lr_scheduler._LRScheduler],
    epochs: int = 100,
    temperature: float = 0.5,
    device: str = "cuda",
) -> list[float]:
    # SimCLR training loop
    # Each batch produces 2*B augmented views (2 per image)
    # Best practice: use LARS optimizer with linear warmup + cosine decay
    # SimCLR benefits from large batch sizes (2048-8192)
    # However, effective batch size = actual_batch * num_gpus * gradient_accum

    model.to(device)
    model.train()
    loss_history: list[float] = []

    for epoch in range(epochs):
        epoch_loss = 0.0
        num_batches = 0

        for (view_i, view_j), _ in dataloader:
            view_i = view_i.to(device)
            view_j = view_j.to(device)

            # Forward pass through both views
            _, z_i = model(view_i)  # Discard representation, keep projection
            _, z_j = model(view_j)

            # Contrastive loss
            loss = nt_xent_loss(z_i, z_j, temperature=temperature)

            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

        if scheduler is not None:
            scheduler.step()

        avg_loss = epoch_loss / max(num_batches, 1)
        loss_history.append(avg_loss)
        print(f"Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.4f}")

    return loss_history
```

## Linear Probing Evaluation

**Linear probing** evaluates representation quality by training a **single linear layer** on top of frozen encoder features. The encoder weights are not updated — only the linear classifier is trained. High linear probe accuracy indicates that the self-supervised representations are linearly separable and therefore semantically meaningful.

```python
def linear_probe(
    encoder: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    repr_dim: int = 2048,
    num_classes: int = 1000,
    epochs: int = 100,
    lr: float = 0.1,
    device: str = "cuda",
) -> float:
    # Linear probing evaluation protocol
    # Freeze encoder, train only a linear classifier on top
    # This measures the quality of learned representations
    # Best practice: use SGD with cosine schedule (not Adam)
    # because linear probes are convex problems

    encoder.to(device).eval()
    linear_head = nn.Linear(repr_dim, num_classes).to(device)

    optimizer = torch.optim.SGD(
        linear_head.parameters(), lr=lr,
        momentum=0.9, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Training
    for epoch in range(epochs):
        linear_head.train()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            with torch.no_grad():
                features = encoder(images)
            logits = linear_head(features)
            loss = F.cross_entropy(logits, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        scheduler.step()

    # Evaluation
    linear_head.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)
            features = encoder(images)
            preds = linear_head(features).argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.shape[0]

    accuracy = correct / total
    return accuracy
```

## Transfer Learning Benchmarks

The standard protocol for evaluating self-supervised representations involves multiple downstream tasks:

1. **ImageNet linear probe**: The primary benchmark. SimCLR achieves ~71% top-1, MoCo v3 ~73%, DINO ViT-B ~78%.
2. **Fine-tuning on small datasets**: Transfer to CIFAR-10/100, Food-101, Flowers-102 with full fine-tuning. This tests whether representations generalize beyond the pretraining domain.
3. **Object detection on COCO/VOC**: Fine-tune a Faster R-CNN with the pretrained backbone. SSL methods now match or exceed supervised pretraining.
4. **k-NN evaluation**: Classify test images by finding the k nearest neighbors in the training set using cosine similarity in representation space. No training required — therefore it measures pure representation quality.

**Pitfall**: Comparing methods across different evaluation protocols is misleading. A method reporting 76% linear probe accuracy with a ViT-Large backbone cannot be fairly compared to 71% with a ResNet-50 backbone. Always control for architecture and training compute when comparing self-supervised methods.

## Summary and Key Takeaways

- **Self-supervised learning** eliminates the need for labeled data by creating supervision from the data itself, achieving representation quality that matches or exceeds supervised pretraining on many downstream tasks.
- **SimCLR** learns by pulling augmented views of the same image together and pushing different images apart via the **NT-Xent loss**; however, it requires very large batch sizes (4096+) for sufficient negatives.
- **MoCo** solves SimCLR's batch size requirement with a momentum encoder and feature queue, making contrastive learning practical on limited hardware — **best practice** when GPU memory is constrained.
- **BYOL** proves that negative pairs are not necessary, using asymmetric prediction to avoid collapse; the **trade-off** is increased sensitivity to implementation details like batch normalization.
- **MAE** brings masked modeling to vision with 75% masking ratio, enabling efficient pretraining because the encoder processes only visible patches.
- **Linear probing** is the standard evaluation protocol: freeze the encoder, train only a linear layer, and measure accuracy. **Best practice** is to report both linear probe and fine-tuning results, because they measure different aspects of representation quality.
- The **projection head** in contrastive learning must be discarded after pretraining — the representation **before** the projection head transfers better to downstream tasks, because the projection head discards information useful for downstream tasks but irrelevant to the contrastive objective.
"""
    ),
]
