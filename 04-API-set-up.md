# Set up

Today we will start again locally and then move to the cloud. So we will let an API, a Prometheus and a Grafana run locally and then move them to the cloud, like we did on Tuesday. But additionally we will add a evidently service that tracks our model and the data in the API.

## The API

We will use the model we created yesterday and the API structure from Tuesday. You can find the code in the `webservice` folder. But we will make a small change:

```python
@app.post("/predict", response_model=TaxiRidePrediction)
def predict_duration(data: TaxiRide):
    prediction = predict("green-taxi-ride-duration", data)
    try:
        response = requests.post(
            f"http://evidently_service:8085/iterate/green_taxi_data",
            data=TaxiRidePrediction(
                **data.dict(), prediction=prediction
            ).model_dump_json(),
            headers={"content-type": "application/json"},
        )
    except requests.exceptions.ConnectionError as error:
        print(f"Cannot reach a metrics application, error: {error}, data: {data}")

    return TaxiRidePrediction(**data.dict(), prediction=prediction)
```

We will add a request post to the predict function. This request will sent the data including the prediction to the evidently service. The service will then store the data and the prediction until the window we set later is full. Then it will calculate the metrics makes them available via an API for Prometheus to scrape. Locally we also have to add the `service account json` to the `webservice` folder. And add the path to this json in the `predict.py` file.

```python
def predict(model_name, data):
    load_dotenv()
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
    SA_KEY = "<path to your service account key>"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_KEY
```

We will also update the data model to fit to the data we will use.

```python
class TaxiRide(BaseModel):
    PULocationID: int
    DOLocationID: int
    trip_distance: float
    passenger_count: int
    fare_amount: float
    total_amount: float
```

And the Dockerfile build this API we need to set the `MLFLOW_TRACKING_URI` as an environment variable.

```dockerfile
# Use the official Python image as the base image
FROM python:3.10-slim-buster

# Set the working directory
WORKDIR /app

# Copy the application code to the working directory
COPY . /app

ENV MLFLOW_TRACKING_URI="<your MLFlow server adress>"

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```



