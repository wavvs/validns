import csv
import dns.resolver
import dns.exception
import sys
import random
import string
import click
import requests
import concurrent.futures
import os
import signal


def fetch_resolvers(reliable, only_valid):
    if only_valid:
        url = 'https://public-dns.info/nameservers.csv'
    else:
        url = 'https://public-dns.info/nameservers-all.csv'

    r = requests.get(url).content.decode().split('\n')
    data = csv.DictReader(r)
    resolvers = []
    for i in data:
        if reliable: 
            if i['reliability'] == '1.00':
                resolvers.append(i['ip_address'])
        else:
            resolvers.append(i['ip_address'])
    return resolvers

def resolve_baseline_domains(resolver, baseline_domains, nameserver):
    resolver.nameservers = [nameserver]
    output = {}
    for k in baseline_domains:
        try:
            answer = resolver.resolve(k)
            output[k] = set([str(i) for i in answer])
        except dns.exception.DNSException:
            return None
    return output

def resolve_nxdomain(resolver, domains, nameserver):
    resolver.nameservers = [nameserver]
    nxdomain = ''.join(random.choice(string.ascii_lowercase) for i in range(16))
    for domain in domains:
        try:
            resolver.resolve("{0}.{1}".format(nxdomain, domain))
            return False
        except dns.resolver.NXDOMAIN:
            pass
        except dns.exception.DNSException:
            return False

        try:
            resolver.resolve("{0}.www.{1}".format(nxdomain, domain))
            return False
        except dns.resolver.NXDOMAIN:
            pass
        except dns.exception.DNSException:
            return False
    
    return True

@click.command()
@click.option('--resolvers', '-n', type=click.Path(exists=True), help='File with resolvers. If\
omitted, public-dns.info resolvers are used')
@click.option('--reliable', type=bool, help='Use only 1.00 reliable resolvers from public-dns.info', default=True)
@click.option('--valid', type=bool, help='Use only valid resolvers from public-dns.info', default=True)
@click.option('--baseline-domains', '-b', type=str, multiple=True, help='Baseline domains to specify', default=[
    "archive.org", 
    "thepiratebay.org", 
    "wikileaks.org",
    "wikipedia.org", 
    "rotten.com"
])
@click.option('--threads', '-t', type=int, default=25)
def validns(resolvers, reliable, valid, baseline_domains, threads):
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    rbaseline = resolve_baseline_domains(resolver, baseline_domains, '1.1.1.1')
    if rbaseline is None:
        print("[*] Could not resolve one of the baseline domains")
        sys.exit(1)

    if resolvers is not None:
        with open(resolvers, 'r') as f:
            ns = f.readlines()
    else:
        ns = fetch_resolvers(reliable, valid)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        tasks = [executor.submit(worker, nameserver, baseline_domains, rbaseline) for nameserver in ns]
        for task in concurrent.futures.as_completed(tasks):
            server = task.result()
            if server is not None:
                print(server) 
            
def worker(nameserver, baseline_domains, rbaseline):
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    rserver = resolve_baseline_domains(resolver, baseline_domains, nameserver)
    if rserver is not None:
        for domain in rbaseline:
            if rbaseline[domain] != rserver[domain]:
                break
        else:
            if resolve_nxdomain(resolver, baseline_domains, nameserver):
                return nameserver
    
    return None

def signal_handler(signal, frame):
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    validns()