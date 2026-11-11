# /// script
# requires-python = ">=3.10"
# dependencies = ["e2b>=2.4", "python-dotenv"]
# ///
"""Build the E2B template that DataPilot sandboxes start from.

It is the E2B Code Interpreter template plus the OpenTelemetry SDK and the
DataPilot runtime, so a new sandbox can send telemetry at once without a
pip install on each start.
"""

from pathlib import Path

from dotenv import load_dotenv
from e2b import Template, default_build_logger

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TEMPLATE_NAME = "datapilot-analyst"

template = (
    Template()
    .from_template("code-interpreter-v1")
    .pip_install(["pyarrow", "opentelemetry-sdk==1.38.0", "opentelemetry-exporter-otlp-proto-http==1.38.0"])
    .copy("sandbox/datapilot_runtime.py", "/opt/datapilot/datapilot_runtime.py")
    .copy("sandbox/make_dataset.py", "/opt/datapilot/make_dataset.py")
)

if __name__ == "__main__":
    # 2 vCPU and 2 GiB is the size of the stock Code Interpreter sandbox.
    info = Template.build(
        template,
        TEMPLATE_NAME,
        cpu_count=2,
        memory_mb=2048,
        on_build_logs=default_build_logger(),
    )
    print(f"built {TEMPLATE_NAME}: {info}")
