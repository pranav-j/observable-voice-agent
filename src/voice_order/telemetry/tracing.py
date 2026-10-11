"""OpenTelemetry traces to Phoenix.

LiveKit Agents creates the spans itself (user_turn, eou_detection, agent_turn, llm_node,
tts_node, function_tool, ...). This sets up where they go, and tags every one of them
with the call's session id, providers and models.
"""

from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.util.types import AttributeValue

PROJECT = "voice-order-agent"


def setup_tracing(
    collector_endpoint: str,
    attributes: dict[str, AttributeValue],
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Install a tracer provider for this job. Call `force_flush()` before the job exits."""
    resource = Resource.create(
        {"service.name": PROJECT, "openinference.project.name": PROJECT}  # Phoenix project
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(exporter or OTLPSpanExporter(endpoint=f"{collector_endpoint}/v1/traces"))
    )
    set_tracer_provider(provider, metadata=attributes)
    return provider
