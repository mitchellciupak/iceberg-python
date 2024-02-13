# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
# pylint:disable=redefined-outer-name
import uuid
from datetime import date, datetime

import pyarrow as pa
import pytest
import pytz
from pyspark.sql import SparkSession

from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import (
    BinaryType,
    BooleanType,
    DateType,
    DoubleType,
    FixedType,
    FloatType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
    TimestamptzType,
)


@pytest.fixture()
def catalog() -> Catalog:
    catalog = load_catalog(
        "local",
        **{
            "type": "rest",
            "uri": "http://localhost:8181",
            "s3.endpoint": "http://localhost:9000",
            "s3.access-key-id": "admin",
            "s3.secret-access-key": "password",
        },
    )

    try:
        catalog.create_namespace("default")
    except NamespaceAlreadyExistsError:
        pass

    return catalog


TEST_DATA_WITH_NULL = {
    'bool': [False, None, True],
    'string': ['a', None, 'z'],
    # Go over the 16 bytes to kick in truncation
    'string_long': ['a' * 22, None, 'z' * 22],
    'int': [1, None, 9],
    'long': [1, None, 9],
    'float': [0.0, None, 0.9],
    'double': [0.0, None, 0.9],
    'timestamp': [datetime(2023, 1, 1, 19, 25, 00), None, datetime(2023, 3, 1, 19, 25, 00)],
    'timestamptz': [
        datetime(2023, 1, 1, 19, 25, 00, tzinfo=pytz.timezone('America/New_York')),
        None,
        datetime(2023, 3, 1, 19, 25, 00, tzinfo=pytz.timezone('America/New_York')),
    ],
    'date': [date(2023, 1, 1), None, date(2023, 3, 1)],
    # Not supported by Spark
    # 'time': [time(1, 22, 0), None, time(19, 25, 0)],
    # Not natively supported by Arrow
    # 'uuid': [uuid.UUID('00000000-0000-0000-0000-000000000000').bytes, None, uuid.UUID('11111111-1111-1111-1111-111111111111').bytes],
    'binary': [b'\01', None, b'\22'],
    'fixed': [
        uuid.UUID('00000000-0000-0000-0000-000000000000').bytes,
        None,
        uuid.UUID('11111111-1111-1111-1111-111111111111').bytes,
    ],
}


TABLE_SCHEMA = Schema(
    NestedField(field_id=1, name="bool", field_type=BooleanType(), required=False),
    NestedField(field_id=2, name="string", field_type=StringType(), required=False),
    NestedField(field_id=3, name="string_long", field_type=StringType(), required=False),
    NestedField(field_id=4, name="int", field_type=IntegerType(), required=False),
    NestedField(field_id=5, name="long", field_type=LongType(), required=False),
    NestedField(field_id=6, name="float", field_type=FloatType(), required=False),
    NestedField(field_id=7, name="double", field_type=DoubleType(), required=False),
    NestedField(field_id=8, name="timestamp", field_type=TimestampType(), required=False),
    NestedField(field_id=9, name="timestamptz", field_type=TimestamptzType(), required=False),
    NestedField(field_id=10, name="date", field_type=DateType(), required=False),
    # NestedField(field_id=11, name="time", field_type=TimeType(), required=False),
    # NestedField(field_id=12, name="uuid", field_type=UuidType(), required=False),
    NestedField(field_id=11, name="binary", field_type=BinaryType(), required=False),
    NestedField(field_id=12, name="fixed", field_type=FixedType(16), required=False),
)


@pytest.fixture(scope="session")
def session_catalog() -> Catalog:
    return load_catalog(
        "local",
        **{
            "type": "rest",
            "uri": "http://localhost:8181",
            "s3.endpoint": "http://localhost:9000",
            "s3.access-key-id": "admin",
            "s3.secret-access-key": "password",
        },
    )


@pytest.fixture(scope="session")
def arrow_table_with_null() -> pa.Table:
    """PyArrow table with all kinds of columns"""
    pa_schema = pa.schema([
        ("bool", pa.bool_()),
        ("string", pa.string()),
        ("string_long", pa.string()),
        ("int", pa.int32()),
        ("long", pa.int64()),
        ("float", pa.float32()),
        ("double", pa.float64()),
        ("timestamp", pa.timestamp(unit="us")),
        ("timestamptz", pa.timestamp(unit="us", tz="UTC")),
        ("date", pa.date32()),
        # Not supported by Spark
        # ("time", pa.time64("us")),
        # Not natively supported by Arrow
        # ("uuid", pa.fixed(16)),
        ("binary", pa.binary()),
        ("fixed", pa.binary(16)),
    ])
    return pa.Table.from_pydict(TEST_DATA_WITH_NULL, schema=pa_schema)


@pytest.fixture(scope="session", autouse=True)
def table_v1_with_null_partitioned(session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    partition_cols = [
        'int',
        'bool',
        'string',
        "string_long",
        "long",
        "float",
        "double",
        "date",
        "timestamptz",
        "timestamp",
        "binary",
    ]  # [, "date", "timestamptz", "timestamp", "binary", "fixed"]
    for partition_col in partition_cols:
        identifier = f"default.arrow_table_v1_with_null_partitioned_on_col_{partition_col}"

        try:
            session_catalog.drop_table(identifier=identifier)
        except NoSuchTableError:
            pass
        nested_field = TABLE_SCHEMA.find_field(partition_col)
        source_id = nested_field.field_id

        tbl = session_catalog.create_table(
            identifier=identifier,
            schema=TABLE_SCHEMA,
            partition_spec=PartitionSpec(
                PartitionField(source_id=source_id, field_id=1001, transform=IdentityTransform(), name=partition_col)
            ),
            properties={'format-version': '1'},
        )
        tbl.append(arrow_table_with_null)

        assert tbl.format_version == 1, f"Expected v1, got: v{tbl.format_version}"


@pytest.fixture(scope="session", autouse=True)
def table_v1_appended_with_null_partitioned(session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    partition_cols = [
        'int',
        'bool',
        'string',
        "string_long",
        "long",
        "float",
        "double",
        "date",
        "timestamptz",
        "timestamp",
        "binary",
    ]
    for partition_col in partition_cols:
        identifier = f"default.arrow_table_v1_appended_with_null_partitioned_on_col_{partition_col}"

        try:
            session_catalog.drop_table(identifier=identifier)
        except NoSuchTableError:
            pass

        nested_field = TABLE_SCHEMA.find_field(partition_col)
        source_id = nested_field.field_id
        tbl = session_catalog.create_table(
            identifier=identifier,
            schema=TABLE_SCHEMA,
            partition_spec=PartitionSpec(
                PartitionField(source_id=source_id, field_id=1001, transform=IdentityTransform(), name=partition_col)
            ),  # name has to be the same for identity transform
            properties={'format-version': '1'},
        )

        for _ in range(2):
            tbl.append(arrow_table_with_null)
        assert tbl.format_version == 1, f"Expected v1, got: v{tbl.format_version}"


@pytest.fixture(scope="session", autouse=True)
def table_v2_with_null_partitioned(session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    partition_cols = [
        'int',
        'bool',
        'string',
        "string_long",
        "long",
        "float",
        "double",
        "date",
        "timestamptz",
        "timestamp",
        "binary",
    ]
    for partition_col in partition_cols:
        identifier = f"default.arrow_table_v2_with_null_partitioned_on_col_{partition_col}"

        try:
            session_catalog.drop_table(identifier=identifier)
        except NoSuchTableError:
            pass
        nested_field = TABLE_SCHEMA.find_field(partition_col)
        source_id = nested_field.field_id

        tbl = session_catalog.create_table(
            identifier=identifier,
            schema=TABLE_SCHEMA,
            partition_spec=PartitionSpec(
                PartitionField(source_id=source_id, field_id=1001, transform=IdentityTransform(), name=partition_col)
            ),
            properties={'format-version': '2'},
        )
        tbl.append(arrow_table_with_null)

        assert tbl.format_version == 2, f"Expected v2, got: v{tbl.format_version}"


@pytest.fixture(scope="session", autouse=True)
def table_v2_appended_with_null_partitioned(session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    partition_cols = [
        'int',
        'bool',
        'string',
        "string_long",
        "long",
        "float",
        "double",
        "date",
        "timestamptz",
        "timestamp",
        "binary",
    ]
    for partition_col in partition_cols:
        identifier = f"default.arrow_table_v2_appended_with_null_partitioned_on_col_{partition_col}"

        try:
            session_catalog.drop_table(identifier=identifier)
        except NoSuchTableError:
            pass

        nested_field = TABLE_SCHEMA.find_field(partition_col)
        source_id = nested_field.field_id
        tbl = session_catalog.create_table(
            identifier=identifier,
            schema=TABLE_SCHEMA,
            partition_spec=PartitionSpec(
                PartitionField(source_id=source_id, field_id=1001, transform=IdentityTransform(), name=partition_col)
            ),
            properties={'format-version': '2'},
        )

        for _ in range(2):
            tbl.append(arrow_table_with_null)
        assert tbl.format_version == 2, f"Expected v2, got: v{tbl.format_version}"


@pytest.fixture(scope="session", autouse=True)
def table_v1_v2_appended_with_null(session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    partition_cols = [
        'int',
        'bool',
        'string',
        "string_long",
        "long",
        "float",
        "double",
        "date",
        "timestamptz",
        "timestamp",
        "binary",
    ]
    for partition_col in partition_cols:
        identifier = f"default.arrow_table_v1_v2_appended_with_null_partitioned_on_col_{partition_col}"

        try:
            session_catalog.drop_table(identifier=identifier)
        except NoSuchTableError:
            pass

        nested_field = TABLE_SCHEMA.find_field(partition_col)
        source_id = nested_field.field_id
        tbl = session_catalog.create_table(
            identifier=identifier,
            schema=TABLE_SCHEMA,
            partition_spec=PartitionSpec(
                PartitionField(source_id=source_id, field_id=1001, transform=IdentityTransform(), name=partition_col)
            ),
            properties={'format-version': '1'},
        )
        tbl.append(arrow_table_with_null)

        assert tbl.format_version == 1, f"Expected v1, got: v{tbl.format_version}"

        with tbl.transaction() as tx:
            tx.upgrade_table_version(format_version=2)

        tbl.append(arrow_table_with_null)

        assert tbl.format_version == 2, f"Expected v2, got: v{tbl.format_version}"


@pytest.mark.integration
@pytest.mark.parametrize(
    "part_col", ['int', 'bool', 'string', "string_long", "long", "float", "double", "date", 'timestamp', 'timestamptz']
)
@pytest.mark.parametrize("format_version", [1, 2])
def test_query_filter_null_partitioned(spark: SparkSession, part_col: str, format_version: int) -> None:
    identifier = f"default.arrow_table_v{format_version}_with_null_partitioned_on_col_{part_col}"
    df = spark.table(identifier)
    for col in TEST_DATA_WITH_NULL.keys():
        assert df.where(f"{col} is not null").count() == 2, f"Expected 2 rows for {col}"

    spark.sql(f"select path from {identifier}.manifests").show(20, False)
    spark.sql(f"select path from {identifier}.manifests").collect()


@pytest.mark.integration
@pytest.mark.parametrize(
    "part_col", ['int', 'bool', 'string', "string_long", "long", "float", "double", "date", "timestamptz", "timestamp", "binary"]
)
@pytest.mark.parametrize("format_version", [1, 2])
def test_query_filter_appended_null_partitioned(spark: SparkSession, part_col: str, format_version: int) -> None:
    identifier = f"default.arrow_table_v{format_version}_appended_with_null_partitioned_on_col_{part_col}"
    df = spark.table(identifier)
    for col in TEST_DATA_WITH_NULL.keys():
        df = spark.table(identifier)
        assert df.where(f"{col} is not null").count() == 4, f"Expected 6 rows for {col}"


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    import importlib.metadata
    import os

    spark_version = ".".join(importlib.metadata.version("pyspark").split(".")[:2])
    scala_version = "2.12"
    iceberg_version = "1.4.3"

    os.environ["PYSPARK_SUBMIT_ARGS"] = (
        f"--packages org.apache.iceberg:iceberg-spark-runtime-{spark_version}_{scala_version}:{iceberg_version},"
        f"org.apache.iceberg:iceberg-aws-bundle:{iceberg_version} pyspark-shell"
    )
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "admin"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "password"

    spark = (
        SparkSession.builder.appName("PyIceberg integration test")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.integration", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.integration.catalog-impl", "org.apache.iceberg.rest.RESTCatalog")
        .config("spark.sql.catalog.integration.uri", "http://localhost:8181")
        .config("spark.sql.catalog.integration.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.integration.warehouse", "s3://warehouse/wh/")
        .config("spark.sql.catalog.integration.s3.endpoint", "http://localhost:9000")
        .config("spark.sql.catalog.integration.s3.path-style-access", "true")
        .config("spark.sql.defaultCatalog", "integration")
        .getOrCreate()
    )

    return spark


@pytest.mark.integeration
@pytest.mark.parametrize(
    "part_col", ['int', 'bool', 'string', "string_long", "long", "float", "double", "date", "timestamptz", "timestamp", "binary"]
)
def test_query_filter_v1_v2_append_null(spark: SparkSession, part_col: str) -> None:
    identifier = f"default.arrow_table_v1_v2_appended_with_null_partitioned_on_col_{part_col}"
    df = spark.table(identifier)
    for col in TEST_DATA_WITH_NULL.keys():
        df = spark.table(identifier)
        assert df.where(f"{col} is not null").count() == 4, f"Expected 4 row for {col}"


@pytest.mark.integration
def test_summaries_with_null(spark: SparkSession, session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    identifier = "default.arrow_table_summaries"

    try:
        session_catalog.drop_table(identifier=identifier)
    except NoSuchTableError:
        pass
    tbl = session_catalog.create_table(
        identifier=identifier,
        schema=TABLE_SCHEMA,
        partition_spec=PartitionSpec(PartitionField(source_id=4, field_id=1001, transform=IdentityTransform(), name="int")),
        properties={'format-version': '2'},
    )

    tbl.append(arrow_table_with_null)
    tbl.append(arrow_table_with_null)

    rows = spark.sql(
        f"""
        SELECT operation, summary
        FROM {identifier}.snapshots
        ORDER BY committed_at ASC
    """
    ).collect()

    operations = [row.operation for row in rows]
    assert operations == ['append', 'append']

    summaries = [row.summary for row in rows]

    assert summaries[0] == {
        'added-data-files': '3',
        'added-files-size': '14471',
        'added-records': '3',
        'total-data-files': '3',
        'total-delete-files': '0',
        'total-equality-deletes': '0',
        'total-files-size': '14471',
        'total-position-deletes': '0',
        'total-records': '3',
    }

    assert summaries[1] == {
        'added-data-files': '3',
        'added-files-size': '14471',
        'added-records': '3',
        'total-data-files': '6',
        'total-delete-files': '0',
        'total-equality-deletes': '0',
        'total-files-size': '28942',
        'total-position-deletes': '0',
        'total-records': '6',
    }


@pytest.mark.integration
def test_data_files_with_table_partitioned_with_null(
    spark: SparkSession, session_catalog: Catalog, arrow_table_with_null: pa.Table
) -> None:
    identifier = "default.arrow_data_files"

    try:
        session_catalog.drop_table(identifier=identifier)
    except NoSuchTableError:
        pass
    tbl = session_catalog.create_table(
        identifier=identifier,
        schema=TABLE_SCHEMA,
        partition_spec=PartitionSpec(PartitionField(source_id=4, field_id=1001, transform=IdentityTransform(), name="int")),
        properties={'format-version': '1'},
    )

    tbl.append(arrow_table_with_null)
    tbl.append(arrow_table_with_null)

    # added_data_files_count, existing_data_files_count, deleted_data_files_count
    rows = spark.sql(
        f"""
        SELECT added_data_files_count, existing_data_files_count, deleted_data_files_count
        FROM {identifier}.all_manifests
    """
    ).collect()

    assert [row.added_data_files_count for row in rows] == [3, 3, 3]
    assert [row.existing_data_files_count for row in rows] == [
        0,
        0,
        0,
    ]
    assert [row.deleted_data_files_count for row in rows] == [0, 0, 0]


@pytest.mark.integration
def test_invalid_arguments(spark: SparkSession, session_catalog: Catalog, arrow_table_with_null: pa.Table) -> None:
    identifier = "default.arrow_data_files"

    try:
        session_catalog.drop_table(identifier=identifier)
    except NoSuchTableError:
        pass

    tbl = session_catalog.create_table(
        identifier=identifier,
        schema=TABLE_SCHEMA,
        partition_spec=PartitionSpec(PartitionField(source_id=4, field_id=1001, transform=IdentityTransform(), name="int")),
        properties={'format-version': '1'},
    )

    with pytest.raises(ValueError, match="Expected PyArrow table, got: not a df"):
        tbl.append("not a df")
