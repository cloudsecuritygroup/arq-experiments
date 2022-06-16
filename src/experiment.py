##
## Copyright 2022 Zachary Espiritu
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##    http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.
##

from __future__ import annotations

from arca.arq import ARQ, Table, RangeQuery, RangeAggregateScheme
from arca.arq.range_aggregate_querier import ResolveDone, ResolveContinue
from arca.ste.edx import MultiprocessEDX
from arca.ste.serializers import IntSerializer, StructSerializer, PickleSerializer
from arca.arq.plaintext_schemes.sum import SumPrefix
from arca.arq.plaintext_schemes.median import MedianAlphaApprox
from arca.arq.plaintext_schemes.minimum import (
    MinimumASTable,
    MinimumLinearEMT,
    MinimumSparseTable,
)
from arca.arq.plaintext_schemes.mode import ModeASTable

from typing import Generic, Optional, TypeVar, List, cast, Any
from columnar import columnar
from dataclasses import dataclass
from collections import defaultdict
from multiprocessing import Process
from tqdm import tqdm, trange

import xmlrpc.client
import xmlrpc.server
import argparse
import sys
import enum
import csv
import time
import gc
import logging
import math
import socket
import strings
import random

AggregateSchemeOutputType = TypeVar("AggregateSchemeOutputType")
EdsType = TypeVar("EdsType")
TokenInputType = TypeVar("TokenInputType")
ResolveOutputType = TypeVar("ResolveOutputType")


class ARQXMLRPCServerInstance:
    def __init__(
        self,
        arq_scheme: ARQ[
            AggregateSchemeOutputType, EdsType, TokenInputType, ResolveOutputType
        ],
    ):
        self.arq_scheme = arq_scheme
        self.eds: Optional[EdsType] = None

    def reset_server(self) -> None:
        self.eds = None
        logging.debug(f"Set self.eds to None.")

    def setup_server(self, eds_serialized: bytes) -> None:
        self.eds = self.arq_scheme.load_eds(eds_serialized)
        logging.debug(
            f"Updated self.eds to new {type(self.eds)} of size {sys.getsizeof(self.eds)} bytes."
        )

    def query_server(self, search_tokens: List[bytes]) -> List[bytes]:
        if self.eds is not None:
            return self.arq_scheme.query_server(search_tokens, self.eds)
        return []


class ARQExperimentServer(
    Generic[AggregateSchemeOutputType, EdsType, TokenInputType, ResolveOutputType]
):
    def __init__(
        self,
        arq_scheme: ARQ[
            AggregateSchemeOutputType, EdsType, TokenInputType, ResolveOutputType
        ],
    ):
        self.arq_scheme = arq_scheme

    def serve_forever(self, hostname: str, port: int) -> None:
        logging.debug(f"Starting server on {hostname}:{port}...")
        with xmlrpc.server.SimpleXMLRPCServer(
            (hostname, port),
            requestHandler=xmlrpc.server.SimpleXMLRPCRequestHandler,
            allow_none=True,
            use_builtin_types=True,
            logRequests=False,
        ) as server:
            server.register_introspection_functions()
            server.register_instance(ARQXMLRPCServerInstance(self.arq_scheme))
            server.serve_forever()


@dataclass(frozen=True)
class SetupExperimentResult:
    setup_time_ns_average: int
    size_eds_bytes: int
    number_of_runs: int


@dataclass(frozen=True)
class QueryExperimentResult:
    setup_time: int
    size_eds_bytes: int
    number_of_runs: int
    query_client_time_avg: int
    query_server_time_avg: int
    number_of_queries: int
    query_client_time_average_buckets: Dict[int, float]
    query_server_time_average_buckets: Dict[int, float]
    queries_per_bucket: Dict[int, int]


class ARQExperimentClient(
    Generic[AggregateSchemeOutputType, EdsType, TokenInputType, ResolveOutputType]
):
    def __init__(
        self,
        arq_scheme: ARQ[
            AggregateSchemeOutputType, EdsType, TokenInputType, ResolveOutputType
        ],
        server_hostname: str,
        server_port: int,
    ):
        self.arq_scheme = arq_scheme
        # self.server_proxy = xmlrpc.client.ServerProxy(
        #     f"http://{server_hostname}:{server_port}", use_builtin_types=True
        # )
        self.key = self.arq_scheme.generate_key()

    def run_setup_experiments(
        self, table: Table, number_of_runs: int
    ) -> SetupExperimentResult:
        setup_time_sum = 0
        size_eds_serialized = 0

        for _ in trange(number_of_runs):
            gc.disable()
            setup_start_time = time.perf_counter_ns()

            key = self.arq_scheme.generate_key()
            eds_serialized = self.arq_scheme.setup(key, table)
            # self.server_proxy.setup_server(eds_serialized)
            self.arq_scheme.load_eds(eds_serialized)

            setup_end_time = time.perf_counter_ns()
            setup_time_sum += setup_end_time - setup_start_time
            gc.enable()

            size_eds_serialized = len(eds_serialized)

            # self.server_proxy.reset_server()

        setup_time_ns_average = setup_time_sum / number_of_runs

        return SetupExperimentResult(
            setup_time_ns_average=setup_time_ns_average,
            size_eds_bytes=size_eds_serialized,
            number_of_runs=number_of_runs,
        )

    def run_query_experiments(self, table: Table) -> QueryExperimentResult:
        logging.debug("Running setup experiments...")
        gc.disable()
        setup_start_time = time.perf_counter_ns()

        key = self.arq_scheme.generate_key()
        eds_serialized = self.arq_scheme.setup(key, table)
        # self.server_proxy.setup_server(eds_serialized)
        eds = self.arq_scheme.load_eds(eds_serialized)

        setup_end_time = time.perf_counter_ns()
        setup_time = setup_end_time - setup_start_time
        gc.enable()

        logging.debug("Done. Collecting garbage...")
        gc.collect()

        logging.debug("Done. Processing statistics...")

        size_eds_serialized = len(eds_serialized)

        query_client_time_sum_all = 0
        query_server_time_sum_all = 0

        query_client_time_sum_buckets = defaultdict(lambda: 0)
        query_client_time_count_buckets = defaultdict(lambda: 0)
        query_server_time_sum_buckets = defaultdict(lambda: 0)
        query_server_time_count_buckets = defaultdict(lambda: 0)

        number_of_runs = 0

        # for range_query in RangeQuery.enumerate_all(table.domain):
        logging.debug("Done. Running query experiments...")
        for bucket, range_query in tqdm(
            RangeQuery.enumerate_samples_from_buckets(
                table.domain, bucket_size=5, num_samples_per_bucket=250
            ),
            total=int(100 / 5 * 250),
            leave=False,
        ):
            scheme_name = type(self.arq_scheme.aggregate_scheme).__name__
            if scheme_name == "MinimumLinearEMT":
                block_size = MinimumLinearEMT.compute_block_size(table.domain.size())
                if range_query.end - range_query.start < block_size:
                    continue

            gc.disable()

            query_server_time = 0
            query_client_time = 0
            query_client_start_time = time.perf_counter_ns()

            arq_querier = self.arq_scheme.generate_querier(
                key=key, domain=table.domain, query=range_query
            )
            subqueries = arq_querier.query()
            while True:
                search_tokens = arq_querier.token(subqueries)

                query_client_end_time = time.perf_counter_ns()
                query_client_time += query_client_end_time - query_client_start_time
                query_server_start_time = time.perf_counter_ns()

                ciphertexts = self.arq_scheme.query_server(search_tokens, eds)

                query_server_end_time = time.perf_counter_ns()
                query_server_time += query_server_end_time - query_server_start_time
                query_client_start_time = time.perf_counter_ns()

                response = arq_querier.resolve(ciphertexts)
                if isinstance(response, ResolveDone):
                    break
                elif isinstance(response, ResolveContinue):
                    subqueries = response.subqueries
                else:
                    raise ValueError("bad")

            query_client_end_time = time.perf_counter_ns()
            query_client_time += query_client_end_time - query_client_start_time

            gc.enable()

            query_client_time_sum_buckets[bucket] += query_client_time
            query_client_time_count_buckets[bucket] += 1
            query_client_time_sum_all += query_client_time
            query_server_time_sum_buckets[bucket] += query_server_time
            query_server_time_count_buckets[bucket] += 1
            query_server_time_sum_all += query_server_time

            number_of_runs += 1

        query_client_time_average_buckets = defaultdict(lambda: 0)
        for bucket, time_sum in query_client_time_sum_buckets.items():
            num_runs_in_bucket = query_client_time_count_buckets[bucket]
            query_client_time_average_buckets[bucket] = time_sum / num_runs_in_bucket

        query_server_time_average_buckets = defaultdict(lambda: 0)
        for bucket, time_sum in query_server_time_sum_buckets.items():
            num_runs_in_bucket = query_server_time_count_buckets[bucket]
            query_server_time_average_buckets[bucket] = time_sum / num_runs_in_bucket

        query_client_time_avg = query_client_time_sum_all / number_of_runs
        query_server_time_avg = query_server_time_sum_all / number_of_runs

        # self.server_proxy.reset_server()

        return QueryExperimentResult(
            setup_time=setup_time,
            size_eds_bytes=size_eds_serialized,
            number_of_runs=number_of_runs,
            query_client_time_avg=query_client_time_avg,
            query_server_time_avg=query_server_time_avg,
            number_of_queries=number_of_runs,
            query_client_time_average_buckets=query_client_time_average_buckets,
            query_server_time_average_buckets=query_server_time_average_buckets,
            queries_per_bucket=query_client_time_count_buckets,
        )

    def run_experiments(self, table: Table) -> QueryExperimentResult:
        query_result = self.run_query_experiments(table)

        return query_result


SCHEME_DICT = {
    SumPrefix.__name__: (SumPrefix, IntSerializer(), IntSerializer()),
    MinimumSparseTable.__name__: (
        MinimumSparseTable,
        StructSerializer(format_string="ii"),
        IntSerializer(),
    ),
    MinimumASTable.__name__: (
        MinimumASTable,
        StructSerializer(format_string="ii"),
        IntSerializer(),
    ),
    MinimumLinearEMT.__name__: (
        MinimumLinearEMT,
        StructSerializer(format_string="iii"),
        IntSerializer(),
    ),
    ModeASTable.__name__: (
        ModeASTable,
        StructSerializer(format_string="ii"),
        StructSerializer(format_string="ii"),
    ),
    MedianAlphaApprox.__name__: (
        MedianAlphaApprox,
        StructSerializer(format_string="ii"),
        PickleSerializer(),
    ),
}


def scheme_parser(
    string: str,
) -> Tuple[
    RangeAggregateScheme[Any, Any, Any], Serializer[Any, Any], Serializer[Any, Any]
]:
    if len(string) <= 0:
        raise ValueError("cannot be empty string")

    tokens = string.split(":")
    scheme_name = tokens[0]
    args = map(float, tokens[1:])

    if scheme_name not in SCHEME_DICT:
        raise ValueError("bad scheme name")

    return (
        SCHEME_DICT[scheme_name][0](*args),
        SCHEME_DICT[scheme_name][1],
        SCHEME_DICT[scheme_name][2],
    )


def process_results(results: List[ARQ, Table, str, QueryExperimentResult]):
    data_headers = [
        strings.AGGREGATE_SCHEME_CSV_HEADER,
        strings.STE_SCHEME_CSV_HEADER,
        strings.DATASET_PATH_HEADER,
        strings.DOMAIN_LOWER_BOUND_HEADER,
        strings.DOMAIN_UPPER_BOUND_HEADER,
        strings.NUM_FILLED_DOMAIN_POINTS_HEADER,
        strings.NUM_RECORDS_HEADER,
        strings.AVG_SETUP_TIME_HEADER,
        strings.EDS_SIZE_HEADER,
        strings.NUM_SETUP_RUNS_HEADER,
        strings.CLIENT_AVG_QUERY_TIME_HEADER,
        strings.SERVER_AVG_QUERY_TIME_HEADER,
        strings.NUM_QUERY_RUNS_HEADER,
    ]
    for bucket in range(5, 101, 5):
        data_headers.append(f"{strings.CLIENT_AVG_QUERY_TIME_HEADER}:{bucket}%")
        data_headers.append(f"{strings.SERVER_AVG_QUERY_TIME_HEADER}:{bucket}%")
        data_headers.append(f"{strings.NUM_QUERY_RUNS_HEADER}:{bucket}%")

    dumped_data = []
    for arq_scheme, table, dataset_path, query_result in results:
        experiment_data = [
            type(arq_scheme.aggregate_scheme).__name__,
            type(arq_scheme.eds_scheme).__name__,
            dataset_path,
            table.domain.start,
            table.domain.end,
            table.number_of_filled_domain_points(),
            table.number_of_records(),
            query_result.setup_time,
            query_result.size_eds_bytes,
            query_result.number_of_runs,
            query_result.query_client_time_avg,
            query_result.query_server_time_avg,
            query_result.number_of_queries,
        ]

        for bucket in range(5, 101, 5):
            experiment_data.append(
                query_result.query_client_time_average_buckets[bucket]
            )
            experiment_data.append(
                query_result.query_server_time_average_buckets[bucket]
            )
            experiment_data.append(query_result.queries_per_bucket[bucket])

        dumped_data.append(experiment_data)

    return (data_headers, dumped_data)


def run_server(arq_scheme, hostname, port):
    server = ARQExperimentServer(arq_scheme)
    server.serve_forever(hostname, port)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Runs the ARQ experiments for [EMT22]."
    )
    parser.add_argument("--version", action="version", version="arq-experiments 1.0")
    parser.add_argument(
        "-s",
        "--scheme",
        nargs="+",
        type=scheme_parser,
        required=True,
        help="the name of the scheme to run",
    )
    parser.add_argument(
        "-d",
        "--dataset",
        nargs="+",
        type=argparse.FileType("r"),
        help="a path to the dataset to run against the scheme",
    )
    parser.add_argument(
        "-q",
        "--query_strategy",
        nargs=1,
        type=str,
        choices=["all", "random"],
        help="if 'all', runs all possible queries against the scheme; if 'random', randomly samples queries to run against the scheme",
    )
    parser.add_argument(
        "-n",
        "--hostname",
        type=str,
        required=True,
        help="the name of the server host",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        required=True,
        help="the port of the server host",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="prints additional information",
    )
    parser.add_argument(
        "--print_output",
        action="store_true",
        help="prints the output as a table in the terminal",
    )
    parser.add_argument(
        "-o",
        "--output_csv_file",
        type=argparse.FileType("w+"),
        help="output file path for experimental results as a CSV",
    )
    parser.add_argument(
        "--num_processes",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--synthetic_sparsity_percent",
        type=int,
    )
    parser.add_argument(
        "--synthetic_domain_size",
        type=int,
    )

    args = parser.parse_args()

    parsed_records = []

    logging.debug(f"Parsing datasets...")
    if args.synthetic_domain_size or args.synthetic_sparsity_percent:
        if args.synthetic_domain_size is None or args.synthetic_sparsity_percent is None:
            parser.error("both --synthetic_domain_size and --synthetic_sparsity_percent must be specified")
        num_records = math.floor(args.synthetic_domain_size * args.synthetic_sparsity_percent / 100)
        records = list((i, 1) for i in random.sample(range(args.synthetic_domain_size), k=num_records))
        parsed_records.append(("synthetic", records))
    elif args.dataset:
        for dataset in args.dataset:
            records = list(map(lambda record: (int(record[0]), 1), csv.reader(dataset)))
            dataset.close()
            parsed_records.append((dataset.name, records))
    else:
        parser.error("--dataset must be specified")

    if args.query_strategy is None:
        parser.error("--query_strategy must be specified if --type client is specified")

    if args.debug:
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logging.basicConfig(
            format=f"[%(filename)s:%(lineno)s:%(funcName)s] %(message)s"
        )

    results = []
    for dataset_name, records in parsed_records:
        table = Table.make(records)
        logging.debug(f"Domain size is {table.domain.size()}; # of records is {len(records)}.")

        for aggregate_scheme, dx_key_serializer, dx_value_serializer in args.scheme:
            scheme_name = type(aggregate_scheme).__name__

            eds_scheme = MultiprocessEDX(
                num_processes=args.num_processes,
                dx_key_serializer=dx_key_serializer,
                dx_value_serializer=dx_value_serializer,
            )
            arq_scheme = ARQ(eds_scheme=eds_scheme, aggregate_scheme=aggregate_scheme)

            logging.debug(f"[{scheme_name}] Running client...")

            client = ARQExperimentClient(arq_scheme, args.hostname, args.port)
            query_result = client.run_experiments(table)
            results.append((arq_scheme, table, dataset_name, query_result))

            logging.debug(
                f"[{scheme_name}] Done with experiments; cleaning up the server."
            )

            logging.debug(f"[{scheme_name}] Done cleaning up.")

    headers, experiment_data = process_results(results)

    if args.output_csv_file:
        writer = csv.writer(args.output_csv_file)
        writer.writerow(headers)
        for row in experiment_data:
            writer.writerow(row)

    if args.print_output:
        print(
            columnar(
                experiment_data,
                headers=headers,
            )
        )


if __name__ == "__main__":
    main()
