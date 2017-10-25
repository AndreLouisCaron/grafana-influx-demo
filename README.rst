.. -*- encoding: utf-8 -*-

===============================================================
  grafana-influx-demo: Demo of Grafana with InfluxDB back-end
===============================================================

This project show cases how to set up Grafana with an InfluxDB back-end using
Docker.

Included:

#. Docker Compose file with InfluxDB and Grafana containers.
#. Python script to spawn containers & provision them with run-time
   configuration:

   * InfluxDB database
   * Grafana data source that pulls data from InfluxDB
   * Grafana dashboard
   * Samples in InfluxDB to showcase the dashboard

 #. Python script to shut everything down.

Python scripts are compatible with both Python 2.7 and Python 3.5.
