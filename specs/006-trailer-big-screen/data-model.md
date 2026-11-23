# Data Model

**MovieDetails** (добавляются поля; у отсутствующих данных значение — пустой список):

- `actors: list[str]`: до 12 имён.
- `related: list[MovieSearchResult]`: до 8 фильмов, без сериалов.

**TrailerVideo**, не сохраняется:

- `id: str`: 11 символов `[A-Za-z0-9_-]`.
- `title: str`: название ролика.
