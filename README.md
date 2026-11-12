# Juggle

Juggle is a proposed semester schedule planner for Colorado School of Mines students. It is designed to help students organize courses, assignments, recurring tasks, and weekly availability across a 15-week semester.

## Planned features

- Add, edit, and remove courses, assignments, and recurring tasks.
- View a semester dashboard and calendar, with courses and task categories distinguished by color.
- Track assignment due dates and receive reminders.
- Record weekly availability and scheduling preferences.
- Use OpenAI GPT-4o-mini to estimate assignment effort and suggest when to work, based on due dates and availability.

## Planned technology

- Frontend: HTML, CSS, and JavaScript
- Backend: Python with Flask and a JSON REST API
- Database: SQLite
- AI integration: OpenAI Python SDK
- Deployment target: Render free tier

## OpenAI API key

An OpenAI API key is a string. Keep it in a local `.env` file and do not commit that file. The repository's `.gitignore` excludes `.env` and related environment files.

Set the value in `.env`:

```dotenv
OPENAI_API_KEY=your_api_key_here
```

When Python reads an environment variable, its value is a string if set and `None` if missing. Validate it before passing it to the OpenAI client:

```python
import os

openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("Set OPENAI_API_KEY in your environment")
```
