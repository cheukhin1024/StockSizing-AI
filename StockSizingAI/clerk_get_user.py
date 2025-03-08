from clerk_backend_api import Clerk

with Clerk(
    bearer_auth="pk_test_Y3VycmVudC1ib2EtODQuY2xlcmsuYWNjb3VudHMuZGV2JA",
) as s:
    res = s.clients.get(client_id="user_2pyUVB5tF59hmjvapsyucIEvj4v")

    if res is not None:
        # handle response
        pass