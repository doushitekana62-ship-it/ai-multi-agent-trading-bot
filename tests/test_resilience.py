from app.supabase_client import execute_data, execute_one, response_data

class R:
    def __init__(self, data): self.data = data

class Q:
    def __init__(self, data): self.data, self.limited = data, None
    def limit(self, n): self.limited = n; return self
    def execute(self): return None if self.data == "none" else R(self.data)

def test_response_data_none():
    assert response_data(None, []) == []
    assert response_data(R(None), {}) == {}

def test_execute_data_none():
    assert execute_data(Q("none"), []) == []
    assert execute_data(Q([{"id": 1}]), []) == [{"id": 1}]

def test_execute_one_uses_limit_and_handles_empty():
    q = Q([{"id": 1}, {"id": 2}])
    assert execute_one(q) == {"id": 1}
    assert q.limited == 1
    assert execute_one(Q([])) is None
    assert execute_one(Q("none")) is None
