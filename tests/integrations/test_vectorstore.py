"""Test TiDB Vector Search functionality."""
from __future__ import annotations

import os
from typing import List, Tuple
import sqlalchemy

import pytest

try:
    from tidb_vector.integrations import TiDBCollection  # noqa

    COLLECTION_NAME = "tidb_vector_index_test"
    CONNECTION_STRING = os.getenv("TEST_TiDB_VECTOR_URL", "")

    if CONNECTION_STRING == "":
        raise OSError("TEST_TiDB_URL environment variable is not set")

    tidb_available = True
except (OSError, ImportError):
    tidb_available = False

ADA_TOKEN_COUNT = 1536


def text_to_embedding(text: str) -> List[float]:
    """Convert text to a unique embedding using ASCII values."""
    ascii_values = [float(ord(char)) for char in text]
    # Pad or trim the list to make it of length ADA_TOKEN_COUNT
    return ascii_values[:ADA_TOKEN_COUNT] + [0.0] * (
        ADA_TOKEN_COUNT - len(ascii_values)
    )


@pytest.fixture(scope="session")
def node_embeddings() -> Tuple[list[str], list[str], list[list[float]], list[dict]]:
    """Return a list of TextNodes with embeddings."""
    ids = [
        "f8e7dee2-63b6-42f1-8b60-2d46710c1971",
        "8dde1fbc-2522-4ca2-aedf-5dcb2966d1c6",
        "e4991349-d00b-485c-a481-f61695f2b5ae",
    ]
    embeddings = [
        text_to_embedding("foo"),
        text_to_embedding("bar"),
        text_to_embedding("baz"),
    ]
    documents = ["foo", "bar", "baz"]
    metadatas = [
        {"page": 1, "category": "P1"},
        {"page": 2, "category": "P1"},
        {"page": 3, "category": "P2"},
    ]
    return (ids, documents, embeddings, metadatas)


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_basic_search(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test end to end construction and search."""

    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    # Add document to the tidb vector
    tidbcol.insert(
        texts=node_embeddings[1], ids=node_embeddings[0], embeddings=node_embeddings[2]
    )

    # similarity search
    results = tidbcol.query(text_to_embedding("foo"), k=3)
    tidbcol.drop_collection()

    # Check results
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == node_embeddings[0][0]


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_get_existing_collection(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test get collection function."""

    # prepare a collection
    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    tidbcol.insert(
        texts=node_embeddings[1],
        ids=node_embeddings[0],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    # try to get the existing collection
    tidbcol2 = TiDBCollection.get_collection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
    )
    results = tidbcol2.query(text_to_embedding("bar"), k=3)
    # delete the collection
    tidbcol2.drop_collection()
    # check the results
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][1]
    assert results[0].distance == 0.0
    assert results[0].id == node_embeddings[0][1]

    # it should fail if the collection had been dropped
    try:
        results = tidbcol.query(text_to_embedding("bar"), k=3)
        assert False, "dropped collection testing raised an error"
    except Exception:
        pass

    # try to get non-existing collection
    try:
        _ = TiDBCollection.get_collection(
            collection_name=COLLECTION_NAME,
            connection_string=CONNECTION_STRING,
        )
        assert False, "non-existing collection testing raised an error"
    except sqlalchemy.exc.NoSuchTableError:
        pass


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_insert(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test insert function."""

    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    # Add document to the tidb vector
    ids = tidbcol.insert(
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    results = tidbcol.query(text_to_embedding("bar"), k=3)

    assert len(results) == 3
    assert results[0].document == node_embeddings[1][1]
    assert results[0].distance == 0.0
    assert results[0].id == ids[1]

    # test insert duplicate ids, it should raise an error
    try:
        _ = tidbcol.insert(
            ids=ids,
            texts=node_embeddings[1],
            embeddings=node_embeddings[2],
            metadatas=node_embeddings[3],
        )
        tidbcol.drop_collection()
        assert False, "inserting to existing collection raised an error"
    except sqlalchemy.exc.IntegrityError:
        tidbcol.drop_collection()
        pass


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_delete(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test delete function."""

    # prepare data
    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    ids = tidbcol.insert(
        ids=node_embeddings[0],
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    results = tidbcol.query(text_to_embedding("foo"), k=3)

    assert len(results) == 3
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == node_embeddings[0][0]

    # test delete by id

    # it should fail to delete first two documents caused by meta filter
    tidbcol.delete([ids[1], ids[0]], filter={"category": "P2"})
    results = tidbcol.query(text_to_embedding("foo"), k=4)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # it should delete the first document just filtered by id
    tidbcol.delete([ids[1], ids[0]])
    results = tidbcol.query(text_to_embedding("foo"), k=4)
    assert len(results) == 1
    assert results[0].document == node_embeddings[1][2]
    assert results[0].distance == 0.004691842206844599
    assert results[0].id == node_embeddings[0][2]

    # insert the document back with different id
    ids = tidbcol.insert(
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    results = tidbcol.query(text_to_embedding("foo"), k=5)
    assert len(results) == 4
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # test delete first document by filter and ids
    tidbcol.delete([ids[1], ids[0]], filter={"page": 1})
    results = tidbcol.query(text_to_embedding("foo"), k=5)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][1]
    assert results[1].document == node_embeddings[1][2]
    assert results[1].distance == results[2].distance

    # insert the document back with different id
    ids = tidbcol.insert(
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )
    results = tidbcol.query(text_to_embedding("foo"), k=10)
    assert len(results) == 6
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # test delete documents by filters
    tidbcol.delete(filter={"category": "P1"})
    results = tidbcol.query(text_to_embedding("foo"), k=10)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][2]
    assert results[1].document == node_embeddings[1][2]
    assert results[0].distance == results[1].distance
    assert results[1].distance == results[2].distance

    # test delete non_extsting by filter
    tidbcol.delete(filter={"category": "P1"})
    results = tidbcol.query(text_to_embedding("foo"), k=10)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][2]
    assert results[1].document == node_embeddings[1][2]
    assert results[0].distance == results[1].distance
    assert results[1].distance == results[2].distance

    # test delete non_extsting by ids
    tidbcol.delete([ids[1], ids[0]])
    results = tidbcol.query(text_to_embedding("foo"), k=10)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][2]
    assert results[1].document == node_embeddings[1][2]
    assert results[0].distance == results[1].distance
    assert results[1].distance == results[2].distance

    # test delete non_extsting by filter and ids
    tidbcol.delete([ids[1], ids[0]], filter={"category": "P1"})
    results = tidbcol.query(text_to_embedding("foo"), k=10)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][2]
    assert results[1].document == node_embeddings[1][2]
    assert results[0].distance == results[1].distance
    assert results[1].distance == results[2].distance

    tidbcol.drop_collection()


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_query(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test query function."""

    # prepare data
    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    ids = tidbcol.insert(
        ids=node_embeddings[0],
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    results = tidbcol.query(text_to_embedding("foo"), k=3)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # test query by matched filter
    results = tidbcol.query(text_to_embedding("foo"), k=3, filter={"category": "P1"})
    assert len(results) == 2
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # test query by matched filter
    results = tidbcol.query(text_to_embedding("foo"), k=3, filter={"category": "P2"})
    assert len(results) == 1
    assert results[0].document == node_embeddings[1][2]
    assert results[0].distance == 0.004691842206844599
    assert results[0].id == ids[2]

    # test query by unmatched filter
    results = tidbcol.query(text_to_embedding("foo"), k=3, filter={"category": "P3"})
    assert len(results) == 0

    # test basic filter query
    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"page": 2, "category": "P1"}
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"page": 1, "category": "P2"}
    )
    assert len(results) == 0

    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"page": {"$gt": 1}, "category": "P1"}
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"page": {"$gt": 1}, "category": {"$ne": "P2"}},
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"page": {"$gt": 1}, "category": {"$ne": "P1"}},
    )
    assert len(results) == 1
    assert results[0].distance == 0.004691842206844599

    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"page": {"$in": [2, 3]}}
    )
    assert len(results) == 2
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"page": {"$in": [2, 3]}, "category": {"$ne": "P1"}},
    )
    assert len(results) == 1
    assert results[0].distance == 0.004691842206844599

    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"page": {"$nin": [2, 3]}}
    )
    assert len(results) == 1
    assert results[0].distance == 0.0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"page": {"$nin": [2, 3]}, "category": {"$ne": "P1"}},
    )
    assert len(results) == 0

    results = tidbcol.query(text_to_embedding("foo"), k=3, filter={"page": {"$gte": 2}})
    assert len(results) == 2
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(text_to_embedding("foo"), k=3, filter={"page": {"$lt": 4}})
    assert len(results) == 3
    assert results[0].distance == 0.0

    results = tidbcol.query(text_to_embedding("baz"), k=3, filter={"page": {"$lte": 2}})
    assert len(results) == 2
    assert results[0].distance == 0.0005609046916807969

    results = tidbcol.query(text_to_embedding("baz"), k=3, filter={"page": {"$eq": 2}})
    assert len(results) == 1
    assert results[0].distance == 0.0005609046916807969

    try:
        _ = tidbcol.query(text_to_embedding("foo"), k=3, filter={"$and": [{"$gt": 1}]})
        tidbcol.drop_collection()
        assert False, "query with invalid filter raised an error"
    except ValueError:
        pass

    tidbcol.drop_collection()


@pytest.mark.skipif(not tidb_available, reason="tidb is not available")
def test_complex_query(
    node_embeddings: Tuple[list[str], list[str], list[list[float]], list[dict]]
) -> None:
    """Test complex query function."""

    # prepare data
    tidbcol = TiDBCollection(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )

    ids = tidbcol.insert(
        ids=node_embeddings[0],
        texts=node_embeddings[1],
        embeddings=node_embeddings[2],
        metadatas=node_embeddings[3],
    )

    results = tidbcol.query(text_to_embedding("foo"), k=3)
    assert len(results) == 3
    assert results[0].document == node_embeddings[1][0]
    assert results[0].distance == 0.0
    assert results[0].id == ids[0]

    # test complex query
    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"$and": [{"page": 1}]}
    )
    assert len(results) == 1
    assert results[0].distance == 0.0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"$and": [{"page": {"$gt": 1}}, {"category": "P1"}]},
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"), k=3, filter={"$or": [{"page": 1}]}
    )
    assert len(results) == 1
    assert results[0].distance == 0.0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"$or": [{"page": {"$gt": 1}}, {"category": "P1"}]},
    )
    assert len(results) == 3
    assert results[0].distance == 0.0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$and": [{"page": {"$gt": 1}}, {"category": "P1"}],
            "$or": [{"page": {"$gt": 1}}, {"category": "P1"}],
        },
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"$and": [{"page": {"$gt": 1}}, {"category": "P1"}], "page": 1},
    )
    assert len(results) == 0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={"$or": [{"page": {"$gt": 1}}, {"category": "P1"}], "page": 1},
    )
    assert len(results) == 1
    assert results[0].distance == 0.0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$and": [{"page": {"$gt": 1}}, {"category": "P1"}],
            "page": 2,
            "$or": [{"page": {"$gt": 1}}, {"category": "P1"}],
        },
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$and": [
                {
                    "$and": [
                        {"page": {"$gt": 1}},
                        {"page": {"$lt": 3}},
                    ],
                    "category": "P2",
                }
            ]
        },
    )
    assert len(results) == 0

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$and": [
                {
                    "$and": [
                        {"page": {"$gt": 1}},
                        {"page": {"$lt": 3}},
                    ],
                    "$or": [
                        {"page": {"$gt": 2}},
                        {"category": {"$eq": "P1"}},
                    ],
                }
            ]
        },
    )
    assert len(results) == 1
    assert results[0].distance == 0.0022719614199674387

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$or": [
                {
                    "$and": [
                        {"page": {"$gt": 1}},
                        {"page": {"$lt": 3}},
                    ],
                    "category": "P2",
                },
                {
                    "category": "P2",
                },
            ]
        },
    )
    assert len(results) == 1
    assert results[0].distance == 0.004691842206844599

    results = tidbcol.query(
        text_to_embedding("foo"),
        k=3,
        filter={
            "$or": [
                {
                    "$and": [
                        {"page": {"$gt": 1}},
                        {"page": {"$lt": 3}},
                    ],
                    "$or": [
                        {"page": {"$lt": 3}},
                        {"category": {"$eq": "P2"}},
                    ],
                },
                {
                    "category": "P2",
                },
            ]
        },
    )
    assert len(results) == 2
    assert results[0].distance == 0.0022719614199674387

    tidbcol.drop_collection()