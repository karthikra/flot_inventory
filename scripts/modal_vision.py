"""Modal deployment for Qwen2.5-VL-7B with vLLM (OpenAI-compatible API).

Deploy:
    modal deploy scripts/modal_vision.py

The endpoint serves an OpenAI-compatible API at:
    https://<user>--qwen25vl-server-serve.modal.run/v1/chat/completions

Configure the app:
    INVENTORY_VISION_BACKEND=openai
    INVENTORY_OPENAI_VISION_URL=https://<user>--qwen25vl-server-serve.modal.run/v1
"""

import modal

MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
REVISION = "main"
GPU = "A10G"

app = modal.App("qwen25vl-server")

# Pre-build image with vLLM and dependencies
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.6.0",
        "transformers>=4.45.0",
        "torch>=2.4.0",
        "qwen-vl-utils",
    )
)

# Volume for caching model weights across cold starts
model_volume = modal.Volume.from_name("qwen25vl-weights", create_if_missing=True)
MODEL_DIR = "/models"


@app.function(
    image=vllm_image,
    gpu=GPU,
    volumes={MODEL_DIR: model_volume},
    container_idle_timeout=300,
    timeout=600,
)
def download_model():
    """Download model weights into the persistent volume."""
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL_ID,
        revision=REVISION,
        local_dir=f"{MODEL_DIR}/{MODEL_ID}",
    )
    model_volume.commit()


@app.cls(
    image=vllm_image,
    gpu=GPU,
    volumes={MODEL_DIR: model_volume},
    container_idle_timeout=300,
    timeout=600,
    allow_concurrent_inputs=4,
)
class Model:
    @modal.enter()
    def start_engine(self):
        from vllm.engine.arg_utils import AsyncEngineArgs
        from vllm.engine.async_llm_engine import AsyncLLMEngine

        args = AsyncEngineArgs(
            model=f"{MODEL_DIR}/{MODEL_ID}",
            revision=REVISION,
            max_model_len=4096,
            dtype="half",
            gpu_memory_utilization=0.90,
            enforce_eager=True,
            limit_mm_per_prompt={"image": 1},
        )
        self.engine = AsyncLLMEngine.from_engine_args(args)

    @modal.web_server(port=8000, startup_timeout=120)
    def serve(self):
        import subprocess

        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", f"{MODEL_DIR}/{MODEL_ID}",
            "--revision", REVISION,
            "--host", "0.0.0.0",
            "--port", "8000",
            "--max-model-len", "4096",
            "--dtype", "half",
            "--gpu-memory-utilization", "0.90",
            "--enforce-eager",
            "--limit-mm-per-prompt", "image=1",
        ]
        subprocess.Popen(cmd)
