# API Mutation Testing

This folder's mutation testing targets the uploaded API-layer code:

- `api/filters.py`
- `api/metadata.py`
- `api/permissions.py`
- `api/serializers.py`
- `api/urls.py`
- `api/views.py`

## Recommended run

```bash
pipenv run mutmut run
pipenv run mutmut results | tee stad_test/report/api_mutation_result.txt
```

## Good mutant targets to watch

- remove `data.pop("description")` in `metadata.py`
- flip `hasattr(view, "filterset_fields")` behavior
- remove `timer.stop()` in serializer validation
- change default-user assignment in `TimerSerializer.validate`
- remove `timer.restart()` in `TimerViewSet.restart`
- remove extra route registration behavior in `CustomRouterWithExtraPaths`
