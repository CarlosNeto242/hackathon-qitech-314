FROM python:3.11-slim

RUN adduser --system --no-create-home user
WORKDIR /mock
COPY server.py /mock/server.py
USER user

CMD ["python", "-u", "server.py"]
