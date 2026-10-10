import base64
import json
import sys

from pycrdt import Doc, Map, Text


def decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def main() -> None:
    request = json.loads(sys.stdin.readline())
    document = Doc()
    document["body"] = Text()
    document["metadata"] = Map()
    document.apply_update(decode(request["initial_update"]))
    if str(document["body"]) != "Solicitud académica":
        raise ValueError(
            f"Python read unexpected Y.Text content: {str(document['body'])!r}"
        )
    metadata = dict(document["metadata"])
    if metadata.get("document_type") != "SOL" or metadata.get("topic") != "aulas":
        raise ValueError("Python failed to read the JavaScript Y.Map metadata")

    document["body"].insert(len(document["body"]), " respuesta")
    document["metadata"]["server_note"] = "saved"
    response_update = document.get_update(decode(request["initial_state_vector"]))
    response = {
        "server_update": encode(response_update),
        "server_state_vector": encode(document.get_state()),
    }
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

    reconnect = json.loads(sys.stdin.readline())
    document.apply_update(decode(reconnect["reconnect_update"]))
    if "edición reconectada" not in str(document["body"]):
        raise ValueError("Python failed to apply the reconnect update")
    if dict(document["metadata"]).get("client_note") != "reconnected":
        raise ValueError("Python failed to apply the reconnect metadata")

    reconnect_update = document.get_update(
        decode(reconnect["client_state_vector"])
    )
    peer_update = document.get_update(decode(reconnect["peer_state_vector"]))
    sys.stdout.write(
        json.dumps(
            {
                "reconnect_update": encode(reconnect_update),
                "peer_update": encode(peer_update),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
