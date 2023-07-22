from fastapi import FastAPI
from data_model import TaxiRide, TaxiRidePrediction
from predict import predict
import requests
import json
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)


@app.get("/")
def index():
    return {"message": "NYC Taxi Ride Duration Prediction"}


@app.post("/predict", response_model=TaxiRidePrediction)
def predict_duration(data: TaxiRide):
    prediction = predict("green-taxi-trip-duration-linear", data)
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