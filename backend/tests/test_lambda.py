import json

from app.main import handler


class LambdaContext:
    function_name = "foodie-api-test"
    aws_request_id = "test-request"


def test_lambda_handler_serves_health_route():
    event = {
        "version": "2.0",
        "routeKey": "GET /healthz",
        "rawPath": "/healthz",
        "rawQueryString": "",
        "headers": {"host": "example.execute-api.us-east-1.amazonaws.com"},
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "test-api",
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "example",
            "http": {
                "method": "GET",
                "path": "/healthz",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "test-request",
            "routeKey": "GET /healthz",
            "stage": "$default",
            "time": "21/Aug/2026:00:00:00 +0000",
            "timeEpoch": 1787270400000,
        },
        "isBase64Encoded": False,
    }

    response = handler(event, LambdaContext())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}
