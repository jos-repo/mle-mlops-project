## The Prometheus Service

We will use the same Prometheus service as on Tuesday. But we will add a new scrape job to the `prometheus.yml` file.

```yaml
global:
  scrape_interval: 30s
  scrape_timeout: 10s

rule_files:
  - alert.yml

scrape_configs:
  - job_name: services
    metrics_path: /metrics
    static_configs:
      - targets:
          - 'prometheus:9090'
          - 'model-service:8080'
          - 'evidently_service:8085'
```

## The Grafana Service

We will use the same Grafana service as on Tuesday. But we will add a new dashboard to the `grafana/dashboards` folder. 
The dashboard we will add is the `data drift` dashboard from evidently.



## The Docker Compose File

Now we will create a docker compose file to run all the services together. 

```yaml
version: '3.7'

services:
  model-service:
        build:
            context: webservice
            dockerfile: Dockerfile
        ports:
            - 8080:8080

  prometheus:
      image: prom/prometheus:v2.21.0
      ports:
          - 9090:9090
      volumes:
          - ./prometheus:/etc/prometheus
          - prometheus-data:/prometheus
      command: --web.enable-lifecycle  --config.file=/etc/prometheus/prometheus.yml

  grafana:
      image: grafana/grafana
      ports:
          - 3000:3000
      restart: unless-stopped
      volumes:
          - ./grafana:/etc/grafana/
          - grafana-data:/var/lib/grafana

  evidently_service:
    build:
      context: evidently_service
      dockerfile: Dockerfile
    depends_on:
      - grafana
    ports:
      - "8085:8085"

volumes:
    grafana-data:
    prometheus-data:
```

This docker compose file will start all the services we need. The `model-service` will be available on port `8080`, the `prometheus` service on port `9090`, the `grafana` service on port `3000` and the `evidently_service` on port `8085`.

## Run the Services

Now we can run the services with the following command:

```bash
docker-compose up -d
```

## Test the Services

Now we can test the services. First we will send a request to the API to get a prediction. We will use the following command:

```bash
curl -X 'POST' \
  'http://localhost:8080/predict' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "PULocationID": 1,
  "DOLocationID": 2,
  "trip_distance": 1.5,
  "passenger_count": 1,
  "fare_amount": 10.0,
  "total_amount": 12.0
}'
```

If you get a correct response you can download two datasets with:

```bash
wget -P ./data https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2022-02.parquet
```

And run the `send_data.py` file. To send more data to the API. You can now check in the `grafana` dashboard if a data drift is detected or if you have no data drift. You can also try to change the `window_size` in the `config.yaml` file to see how it affects the data drift detection. Of course you need to rebuild your services with:

```bash
docker-compose up --build
```
