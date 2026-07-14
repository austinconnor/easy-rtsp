# NVIDIA Triton Inference Server

Triton is a model-serving boundary, not a media transport. easy-rtsp decodes the video and owns the output stream; a transform converts selected frames to tensors and calls Triton over HTTP or gRPC.

```text
RTSP camera → easy-rtsp → preprocess → Triton → draw result → RTSP output
                                      HTTP/gRPC
```

## Install the HTTP client

In your application project:

```console
uv add "tritonclient[http]" opencv-python-headless easy-rtsp
```

The Triton client is deliberately not an easy-rtsp dependency.

## Minimal synchronous transform

This example demonstrates the transport pattern. Change the model, tensor names, input size, color conversion, normalization, and post-processing to match the model configuration.

```python
import cv2
import numpy as np
import tritonclient.http as httpclient
from tritonclient.utils import np_to_triton_dtype

from easy_rtsp import Stream


class TritonTransform:
    def __init__(
        self,
        *,
        server_url: str,
        model_name: str,
        input_name: str,
        output_name: str,
        input_size: tuple[int, int],
    ) -> None:
        self.client = httpclient.InferenceServerClient(url=server_url)
        self.model_name = model_name
        self.input_name = input_name
        self.output_name = output_name
        self.input_size = input_size

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, self.input_size)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = np.transpose(rgb.astype(np.float32), (2, 0, 1))[None, ...]

        request = httpclient.InferInput(
            self.input_name,
            tensor.shape,
            np_to_triton_dtype(tensor.dtype),
        )
        request.set_data_from_numpy(tensor)
        requested_output = httpclient.InferRequestedOutput(self.output_name)

        response = self.client.infer(
            model_name=self.model_name,
            inputs=[request],
            outputs=[requested_output],
        )
        result = response.as_numpy(self.output_name)

        cv2.putText(
            frame,
            f"Triton output: {result.shape}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        return frame


transform = TritonTransform(
    server_url="127.0.0.1:8000",
    model_name="detector",
    input_name="images",
    output_name="output0",
    input_size=(640, 640),
)

stream = (
    Stream.open("rtsp://camera/live")
    .map(transform)
    .serve("annotated", lan_access=True)
)
stream.wait()
```

!!! important "Model preprocessing is part of the contract"
    The example only converts BGR to RGB, resizes, casts to FP32, and creates an NCHW batch. Many models also require scaling, mean/std normalization, letterboxing, or different layouts and tensor names. Match Triton's model metadata and `config.pbtxt`.

## Check readiness before streaming

Fail before opening the camera when the server or model is unavailable:

```python
if not transform.client.is_server_ready():
    raise RuntimeError("Triton is not ready")
if not transform.client.is_model_ready(transform.model_name):
    raise RuntimeError(f"Model {transform.model_name!r} is not ready")
```

## Avoid a request backlog

The simple transform performs one blocking request per processed frame. It is appropriate for a first pipeline and for models faster than the desired frame interval.

For production edge pipelines:

1. Sample inference and reuse the latest result when every frame does not need a new prediction.
2. Put a hard timeout around remote requests.
3. Use a bounded latest-frame queue instead of an unbounded FIFO.
4. Consider Triton's asynchronous HTTP/gRPC client APIs.
5. Batch across cameras only when the model and latency target benefit from it.
6. Measure decode, preprocess, network, queue, inference, postprocess, and encode separately.

Triton's official [client documentation](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/client/README.html) covers HTTP/gRPC clients, asynchronous requests, compression, and shared memory.

## Same device or remote server?

| Placement | Good fit | Watch for |
| --- | --- | --- |
| Same edge device | Simple deployment; low network latency | CPU/GPU contention with decode and encode |
| LAN GPU server | Several edge devices share models | Network jitter, authentication, request bursts |
| Cloud/data center | Central model operations | WAN latency and loss; rarely suitable for every video frame |

Do not expose an unrestricted Triton management endpoint directly to an untrusted network. Put authentication and TLS at the service boundary appropriate for the deployment.
