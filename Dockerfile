FROM python:3.11-slim

# git: cloning / scanning (code_specialised_analysis.py and the full analysis)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — results are written to the mounted results/ volume
RUN useradd -m -u 1000 pipeline

WORKDIR /app

# Dependencies first (better layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code; results/ and inputs/ are volume-mounted at runtime (see docker-compose.yml)
COPY --chown=pipeline:pipeline *.py ./
COPY --chown=pipeline:pipeline core_helpers/ ./core_helpers/
COPY --chown=pipeline:pipeline report_helpers/ ./report_helpers/
COPY --chown=pipeline:pipeline full_analysis/ ./full_analysis/
COPY --chown=pipeline:pipeline inputs/ ./inputs/

RUN mkdir -p results && chown pipeline:pipeline results

USER pipeline

# Run any script: docker compose run --rm pipeline search.py -t mt
ENTRYPOINT ["python"]
CMD ["specialised_report.py", "--help"]
