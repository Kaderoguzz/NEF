import os


from core_crowler.utils.logger import setup_logger
from core_crowler.cores.O5GS.location.ue_info_parser import UEInfoParser
from core_crowler.cores.O5GS.location.log_simulator import FileLogSimulator
from core_crowler.cores.O5GS.location.log_fetching import DockerLogFetcher
from core_crowler.cores.O5GS.location.log_parser import LogParser  

# Need changes
MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASS = os.getenv("MONGO_PASS", "secret")
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "amf_logs")

FILE_FETCHER_ENABLED = os.getenv("FILE_FETCHER_ENABLED", "false").lower()
CONTAINER_FETCHER_ENABLED = os.getenv("CONTAINER_FETCHER_ENABLED", "true").lower()
AMF_FETCHER_ENDPOINT = os.getenv("AMF_FETCHER_ENDPOINT", "amf")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "2"))
AMARISOFT_SERVER = os.getenv("AMARISOFT_SERVER")

MONGO_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}"

# Parser and simulator setup
parser = LogParser(
    mongo_uri=MONGO_URI,
    db_name=MONGO_DB_NAME,
    collection_name="ue_events"
)

# def handle_logs(logs):
#     for log in logs:
#         parser.process_line(log)

if __name__ == "__main__":
    # Logger setup
    logger = setup_logger(logger_name="amf_log_parser")
    if CONTAINER_FETCHER_ENABLED == "true":
        simulator = DockerLogFetcher(
            container_name="amf",
            poll_interval=POLL_INTERVAL
        )
        try:
            #simulator.run(handle_logs)
            simulator.run(parser.process_line)
        except KeyboardInterrupt:
            logger.info("\n[INTERRUPT] Displaying final event history...")
    elif FILE_FETCHER_ENABLED == "true":
        logger = setup_logger(logger_name="amf_log_simulator")
        LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "/data/threeUEs_amf_logs.txt")

        simulator = FileLogSimulator(
            filepath=LOG_FILE_PATH,
            poll_interval=POLL_INTERVAL
        )
        try:
            simulator.run_polling_loop(parser.process_line)
        except KeyboardInterrupt:
            logger.info("\n[INTERRUPT] Displaying final event history...")
    else:
        simulator = UEInfoParser(
            connection_url=AMF_FETCHER_ENDPOINT,
            poll_interval=POLL_INTERVAL,
            mongo_uri=MONGO_URI,
            db_name=MONGO_DB_NAME,
            amarisoft_server=AMARISOFT_SERVER,
        )
        try:          
            simulator.run()
        except KeyboardInterrupt:
            logger.info("\n[INTERRUPT] Stopped UE info polling.")
