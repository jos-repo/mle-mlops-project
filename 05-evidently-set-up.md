## The Evidently Service

To be able to use evidently on real time data we need to set up a evidently service. They provide an example in this [article](https://www.evidentlyai.com/blog/evidently-and-grafana-ml-monitoring-live-dashboards) which can be also found in this [repository](https://github.com/evidentlyai/evidently/tree/main/examples/integrations/grafana_monitoring_service). It is still in development and not perfect but it is good enough. For us to be able to use it we need to change their example a little bit. We will change the `config.yaml` file to fit our data.

```yaml
column_mapping:
  categorical_features:
  - PULocationID
  - DOLocationID
  numerical_features:
  - trip_distance
  - passenger_count
  - fare_amount
  - total_amount
  prediction: prediction
data_format:
  header: true
  separator: ','

service:
  calculation_period_sec: 20
  min_reference_size: 40000
  moving_reference: false
  reference_path: ./green_taxi_data/reference.csv
  use_reference: true
  window_size: 250
  monitors:
  - data_drift
```

Here we define the features our prediction column and the data format. But we also define the settings for our service the calculation period, the minimum reference size, the window size and the monitors we want to use. We will use the `data_drift` monitor. So we will only look for the data drift including in the prediction.

The reference data is the data we will use to compare the real time data to. We will use the data we used to train our model. You can find it under `evidently_service/green_taxi_data/reference.csv`. 

We will also change the `app.py` quite a bit because in the example they simply read data from a csv file and didn't use real time data. If you look at the `app.py` in the `evidently_service` folder you will see that they are using `Flask` instead of `fastAPI` but the structure is quite similar. 

The first thing we will change compared to the example is the `configure_service` function. We will divide it into two functions. One to configure the service and one to start the service. And we will remove the loading of the example data.

```python
def getDriftMonitoringService(config):
    loader = DataLoader()
    logging.info(f"config: {config}")
    options = MonitoringServiceOptions(**config["service"])

    reference_data = loader.load(
        options.reference_path,
        DataOptions(
            date_column=config["data_format"].get("date_column", None),
            separator=config["data_format"]["separator"],
            header=config["data_format"]["header"],
        ),
    )
    logging.info(f"reference dataset loaded: {len(reference_data)} rows")
    svc = MonitoringService(
        reference_data,
        options=options,
        column_mapping=ColumnMapping(**config["column_mapping"]),
    )
    return svc
```

Here we define our `MonitoringService` in evidently with the help of the `config.yaml` file. And load our reference data. The `MonitoringService` we define in the class below:

```python 
class MonitoringService:
    metric: Dict[str, prometheus_client.Gauge]
    last_run: Optional[datetime.datetime]

    def __init__(
        self,
        reference: pd.DataFrame,
        options: MonitoringServiceOptions,
        column_mapping: ColumnMapping = None,
    ):
        self.monitoring = ModelMonitoring(
            monitors=[EVIDENTLY_MONITORS_MAPPING[k]() for k in options.monitors],
            options=[],
        )

        if options.use_reference:
            self.reference = reference.iloc[: -options.window_size, :].copy()
            self.current = pd.DataFrame()
        else:
            self.reference = reference.copy()
            self.current = pd.DataFrame().reindex_like(reference).dropna()
        self.column_mapping = column_mapping
        self.options = options
        self.metrics = {}
        self.next_run_time = None
        self.new_rows = 0
        self.hash = hashlib.sha256(
            pd.util.hash_pandas_object(self.reference).values
        ).hexdigest()
        self.hash_metric = prometheus_client.Gauge(
            "evidently:reference_dataset_hash", "", labelnames=["hash"]
        )

    def iterate(self, new_rows: pd.DataFrame):
        rows_count = new_rows.shape[0]

        self.current = self.current.append(new_rows, ignore_index=True)
        self.new_rows += rows_count
        current_size = self.current.shape[0]
        if self.new_rows < self.options.window_size < current_size:
            self.current.drop(
                index=list(range(0, current_size - self.options.window_size)),
                inplace=True,
            )
            self.current.reset_index(drop=True, inplace=True)

        if current_size < self.options.window_size:
            logging.info(
                f"Not enough data for measurement: {current_size} of {self.options.window_size}."
                f" Waiting more data"
            )
            return
        if (
            self.next_run_time is not None
            and self.next_run_time > datetime.datetime.now()
        ):
            logging.info(f"Next run at {self.next_run_time}")
            return
        self.next_run_time = datetime.datetime.now() + datetime.timedelta(
            seconds=self.options.calculation_period_sec
        )
        self.monitoring.execute(self.reference, self.current, self.column_mapping)
        self.hash_metric.labels(hash=self.hash).set(1)
        for metric, value, labels in self.monitoring.metrics():
            metric_key = f"evidently:{metric.name}"
            found = self.metrics.get(metric_key)
            if not found:
                found = prometheus_client.Gauge(
                    metric_key,
                    "",
                    () if labels is None else list(sorted(labels.keys())),
                )
                self.metrics[metric_key] = found
            if labels is None:
                found.set(value)
            else:
                found.labels(**labels).set(value)
```

Here we implement the `iterate` function which will be called by the API. This function will add the new data to the current data and then check if the window size is full. If it is full it will calculate the metrics and make them available via an API for Prometheus to scrape. This will happen in this part of the code:

```python
# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(
    app.wsgi_app, {"/metrics": prometheus_client.make_wsgi_app()}
)
```

The last important part of the code is the are the two functions with the flask decorators. The first one is the `startup_event` function which will start the evidently service on API start. The second one is the `iterate` function which is the API endpoint to recieve the data via POST requests.

```python
@app.before_first_request
def startup_event():
    # pylint: disable=global-statement
    global SERVICE
    config_file_name = "config.yaml"
    # try to find a config file, it should be generated via a data preparation script
    if not os.path.exists(config_file_name):
        exit(
            "Cannot find config file for the metrics service. Try to check README.md for setup instructions."
        )

    with open(config_file_name, "rb") as config_file:
        config = yaml.safe_load(config_file)

    SERVICE = getDriftMonitoringService(config)


@app.route("/iterate/<dataset>", methods=["POST"])
def iterate(dataset: str):
    item = flask.request.json

    global SERVICE
    if SERVICE is None:
        return "Internal Server Error: service not found", 500
    logging.info(f"Got Data: {item}")
    data = pd.DataFrame([item])
    logging.info(f"Dataframe: {data.head()}")
    SERVICE.iterate(new_rows=data)
    return "ok"
```

Also for this API we will create a Dockerfile. 

```dockerfile
# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

RUN pip install evidently==0.2.8



CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "--port=8085"]
```