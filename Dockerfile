FROM python:3.11-slim

# git is required for repo cloning (pydriller + subprocess fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — cloned repos and results are written here
RUN useradd -m -u 1000 pipeline

WORKDIR /app

# Install dependencies before copying source (better layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source; results/ is volume-mounted at runtime, not baked in
COPY --chown=pipeline:pipeline \
    main.py analysis.py code_analysis.py non_code_analysis.py \
    report.py search.py config.py utils.py \
    generate_example_data.py \
    ./

COPY --chown=pipeline:pipeline inputs/ ./inputs/

RUN mkdir -p results && chown pipeline:pipeline results

USER pipeline

ENTRYPOINT ["python", "main.py"]
