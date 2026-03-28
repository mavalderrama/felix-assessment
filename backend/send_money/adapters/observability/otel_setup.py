"""Configure ADK's built-in OTel pipeline to export traces to Langfuse.

ADK v1.28 already instruments every agent invocation, LLM call, and tool
execution with OpenTelemetry spans (GenAI semantic conventions).  Langfuse v3
accepts OTel traces via its OTLP HTTP endpoint — so zero custom instrumentation
is needed for core tracing: just wire the exporter here.

ADK also auto-detects OTLP from environment variables:
  OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
We call maybe_set_otel_providers() explicitly so the setup is centralised and
testable, rather than relying purely on env-var detection.
"""
from __future__ import annotations

import base64
import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers


def setup_langfuse_otel(
    langfuse_host: str,
    public_key: str,
    secret_key: str,
) -> None:
    """Wire ADK's OTel pipeline to a Langfuse OTLP endpoint.

    Also propagates ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS to the equivalent
    OTel env var so content capture behaviour is consistent.
    """
    if not public_key or not secret_key:
        return

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    endpoint = f"{langfuse_host.rstrip('/')}/api/public/otel/v1/traces"

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": f"Basic {auth}"},
    )

    hooks = OTelHooks(span_processors=[BatchSpanProcessor(exporter)])
    maybe_set_otel_providers(otel_hooks_to_setup=[hooks])

    # Mirror our PII-control flag to the OTel standard env var
    capture = os.environ.get("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")
    os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture)
