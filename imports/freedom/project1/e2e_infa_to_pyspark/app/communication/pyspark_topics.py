"""Topic type constants for the agentic PySpark codegen pipeline.

Mirrors CLIENT_B_insurance_backend-agent-api/app/communication/pc_topics.py.
Each constant is the topic_type used by @type_subscription and TopicId routing.
"""

# Stage 1 — extract transformation metadata from PowerCenter XML (pub/sub, batched).
PC_EXTRACTION_TOPIC_TYPE = "PCExtractor"
PC_EXTRACTION_RESPONSE_TOPIC_TYPE = "PCExtractionResponse"

# Stage 2 — generate PySpark code node-by-node.
PYSPARK_GENERATION_TOPIC_TYPE = "PySparkGeneration"
PYSPARK_GENERATION_RESPONSE_TOPIC_TYPE = "PySparkGenerationResponse"

# Stage 3 — generate Iceberg write/merge logic for targets.
ICEBERG_WRITER_TOPIC_TYPE = "IcebergWriter"

# Stage 4 — review/validate generated PySpark.
REVIEW_TOPIC_TYPE = "PySparkReview"
