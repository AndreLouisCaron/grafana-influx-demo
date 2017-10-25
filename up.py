# -*- coding: utf-8 -*-


from __future__ import print_function

import json
import os
import re
import requests
import requests.exceptions
import subprocess
import time
import timeit

from datetime import datetime, timedelta

try:
    from urllib.parse import urljoin
except ImportError:
    # py2 compat
    from urlparse import urljoin


def run(command, capture=False):
    subprocess.check_call(command)


def run_capture(command):
    return subprocess.check_output(command).decode('utf-8')


def resolve_docker_ip():
    """Determine IP address for TCP connections to Docker containers."""

    # When talking to the Docker daemon via a UNIX socket, route all TCP
    # traffic to docker containers via the TCP loopback interface.
    docker_host = os.environ.get('DOCKER_HOST', '').strip()
    if not docker_host:
        return '127.0.0.1'

    match = re.match('^tcp://(.+?):\d+$', docker_host)
    if not match:
        raise ValueError(
            'Invalid value for DOCKER_HOST: "%s".' % (docker_host,)
        )
    return match.group(1)


def resolve_port(service_name, internal_port):
    output = run_capture([
        'docker-compose', 'port',
        service_name, str(internal_port),
    ])
    return int(output.strip().split(':', 1)[1])


def wait_until_responsive(check, timeout=30.0, clock=timeit.default_timer):
    responsive = False
    ref = clock()
    now = ref
    while not responsive and (now - ref) < timeout:
        try:
            responsive = check()
        except Exception as error:
            print(error)
        time.sleep(1.0)
    if not responsive:
        raise Exception('Timed out!')


def ping_url(url):
    try:
        rep = requests.get(url)
    except requests.exceptions.ConnectionError:
        return False
    rep.raise_for_status()
    return True


def create_influx_database(url, name):
    """Create a database."""
    print('InfluxDB: creating database "%s".' % (name,))
    rep = requests.post(
        urljoin(url, 'query'),
        params={
            'q': 'CREATE DATABASE %s' % (name,),
        },
    )
    rep.raise_for_status()
    return rep.json()['results']


EPOCH = datetime(1970, 1, 1)


# NOTE: fails if ``d`` is not UTC.
def seconds_since_epoch(d):
    return (d - EPOCH).total_seconds()

def nanoseconds_since_epoch(d):
    return seconds_since_epoch(d) * (10**9)


def push_influx_data(url, database, measurements):
    body = '\n'.join((
        ' '.join((
            m[0],  # TODO: tags
            'value=%.3f' % m[1],
            str(int(nanoseconds_since_epoch(m[2]))),
        ))
        for m in measurements
    ))
    body = body.encode('utf-8')
    rep = requests.post(
        urljoin(url, 'write?db=' + database),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        data=body,
    )
    rep.raise_for_status()
    print (rep.text)


def register_grafana_influx_datasource(grafana_url,
                                       username, password,
                                       name, influx_url, database):
    """Create a new InfluxDB data source."""
    rep = requests.post(
        urljoin(grafana_url, 'api/datasources'),
        auth=(username, password),
        json={
            'name': name,
            'type': 'influxdb',
            'url': influx_url,
            'database': database,
            'access': 'proxy',
            'basicAuth': False,
            },
    )
    try:
        rep.raise_for_status()
    except requests.exceptions.HTTPError as error:
        # might already exist from previous run.
        if error.response.status_code != 409:
            raise
    return rep.json()


def create_grafana_dashboard(grafan_url, username, password, title, data):

    # Upload it.
    rep = requests.post(
        urljoin(grafana_url, 'api/dashboards/db'),
        auth=(username, password),
        json=data,
    )
    try:
        rep.raise_for_status()
    except requests.exceptions.HTTPError as error:
        # might already exist from previous run.
        if error.response.status_code != 412:
            raise
    return rep.json()


# Spawn containers.
run([
    'docker-compose', 'up', '-d',
])

# Resolve URLs based on dynamic bind ports.
docker_ip = resolve_docker_ip()
influx_url = 'http://%s:%d' % (
    docker_ip,
    resolve_port('influxdb', 8086),
)
grafana_url = 'http://%s:%d' % (
    docker_ip,
    resolve_port('grafana', 3000),
)

# Wait until services are ready.
wait_until_responsive(
    check=lambda: ping_url(urljoin(influx_url, 'ping')),
)
wait_until_responsive(
    check=lambda: ping_url(grafana_url),
)

def rjson(path):
    with open(path, 'rb') as stream:
        return json.loads(stream.read().decode('utf-8'))

# Provision the runtime configuration.
create_influx_database(influx_url, 'demo')
register_grafana_influx_datasource(
    grafana_url, username='admin', password='admin',
    influx_url='http://influxdb:8086', name='influx', database='demo',
)
create_grafana_dashboard(
    grafana_url, username='admin', password='admin',
    title='metrics',
    data=rjson('dashboard.json'),
)

# Push some data into InfluxDB to show it in our Grafana dashboard.
now = datetime.utcnow()
push_influx_data(influx_url, 'demo', [
    ('redis_commands', 150, now - timedelta(minutes=5)),
    ('redis_commands', 125, now - timedelta(minutes=4)),
    ('redis_commands', 175, now - timedelta(minutes=3)),
    ('redis_commands', 180, now - timedelta(minutes=2)),
    ('redis_commands', 160, now - timedelta(minutes=1)),
    ('redis_commands', 130, now - timedelta(minutes=0)),
])

# Show the caller where to reach Grafana.
print('GRAFANA:', grafana_url)
print('METRICS DASHBAORD:', urljoin(grafana_url, 'dashboard/db/metrics'))
