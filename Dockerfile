FROM ubuntu:latest
RUN apt-get update -y && \
    apt-get install -y python3.11 python3-pip
WORKDIR /app
COPY requirements.txt .
RUN cat requirements.txt
RUN pip3 install -r requirements.txt
COPY /app /app
EXPOSE 3000
CMD ["python3.11", "app.py"]
