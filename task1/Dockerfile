FROM ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1

WORKDIR /app

ADD german-stopwords.txt german-stopwords.NOTICE retrieve.py /app/
RUN chmod +x /app/retrieve.py
