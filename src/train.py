import os
import argparse
import base64
import pandas as pd
import mlflow
from mlflow.tracking.client import MlflowClient

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error



parser = argparse.ArgumentParser()
parser.add_argument(
    "--cml_run", default=False, action=argparse.BooleanOptionalAction, required=True
)
args = parser.parse_args()
cml_run = args.cml_run

GOOGLE_APPLICATION_CREDENTIALS = "./credentials.json"

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS


# Set up the connection to MLflow
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
# Setup the MLflow experiment
mlflow.set_experiment("green-taxi-trip-duration-xgb")

# Set variables
year = 2021
month = 1
color = "green"
features = ["PULocationID", "DOLocationID", "trip_distance", "passenger_count", "fare_amount", "total_amount"]
target = 'duration'
model_name = "green-taxi-trip-duration-linear"
model_version = 1
new_stage = "Production"

# Download and load the data
if not os.path.exists(f"./data/{color}_tripdata_{year}-{month:02d}.parquet"):
    os.system(f"wget -P ./data https://d37ci6vzurychx.cloudfront.net/trip-data/{color}_tripdata_{year}-{month:02d}.parquet")
df = pd.read_parquet(f"./data/{color}_tripdata_{year}-{month:02d}.parquet")

def calculate_trip_duration_in_minutes(df):
    df["duration"] = (df["lpep_dropoff_datetime"] - df["lpep_pickup_datetime"]).dt.total_seconds() / 60
    df = df[(df["duration"] >= 1) & (df["duration"] <= 60)]
    df = df[(df['passenger_count'] > 0) & (df['passenger_count'] < 8)]
    df = df[features + [target]]
    return df

df_processed = calculate_trip_duration_in_minutes(df)

y=df_processed["duration"]
X=df_processed.drop(columns=["duration"])

X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=42, test_size=0.2)


with mlflow.start_run() as run:
    tags = {
        "model": "linear regression",
        "developer": "<your name>",
        "dataset": f"{color}-taxi",
        "year": year,
        "month": month,
        "features": features,
        "target": target
    }
    mlflow.set_tags(tags)
    
    lr = LinearRegression()
    lr.fit(X_train, y_train)

    y_pred_train = lr.predict(X_train)
    rmse_train = mean_squared_error(y_train, y_pred_train, squared=False)
    mlflow.log_metric("rmse train", rmse_train)

    y_pred_test = lr.predict(X_test)
    rmse_test = mean_squared_error(y_test, y_pred_test, squared=False)
    mlflow.log_metric("rmse test", rmse_test)

    mlflow.sklearn.log_model(lr, "model")
    
    run_id = run.info.run_id
    model_uri = f"runs:/{run_id}/model"
    mlflow.register_model(model_uri=model_uri, name=model_name)


    client.transition_model_version_stage(
    name=model_name,
    version=model_version,
    stage=new_stage,
    archive_existing_versions=False)

if cml_run:
    with open("metrics.txt", "w") as f:
        f.write(f"RMSE on the Train Set: {rmse_train}")
        f.write(f"RMSE on the Test Set: {rmse_test}")