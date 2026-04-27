# bot/data - Prompts and Schemas

System prompt templates, user message templates, and response schemas for the quiz bot's LLM functions.

## Structure

```
bot/data/
  prompts/
    system/     # System prompt templates (Markdown)
    user/       # User message templates (Markdown)
  schemas/      # Expected LLM response shapes (annotated JSON)
```

## Template variables

Both template types use Python's `str.format_map`. The only special variables are:

| Variable | Where | Content |
|----------|-------|---------|
| `{schema}` | system only | Injected automatically from the matching file in `schemas/` |
| `{topic_material}` | system only | Optional context from the knowledge graph or Obsidian vault, passed at call time |

All other variables (e.g. `{problem_prompt}`, `{concept}`) are user message fields passed directly from the calling function.

**Note:** any literal `{` or `}` in a template file must be written as `{{` and `}}`. In practice this only applies if you embed a raw JSON example in the prose - don't do that; put JSON examples in the schema file instead.

## Schemas

Files in `schemas/` are annotated JSON examples. Each value is a human-readable description of the expected type and content. These files serve two purposes:

1. **LLM instruction** - injected verbatim into the system prompt so the model knows the exact output shape required
2. **Code contract** - field names here must match the Pydantic model in `bot/schemas.py`

If you add or rename a field, update **both** the schema file and the corresponding model in `bot/schemas.py`. The JSON file is the authoritative definition visible to the LLM; the Pydantic model is its Python mirror (and validates the LLM's response at runtime).

## Correspondence table

| System prompt | User message | Schema | Pydantic model | Function |
|---------------|-------------|--------|----------------|----------|
| `system/grader.md` | `user/grader.md` | `grade_result.json` | `GradeResult` | `grade_answer` |
| `system/examiner.md` | `user/examiner.md` + `user/examiner_weak_section.md` | `exam_problems.json` | `ExamProblem` | `generate_exam` |
| `system/exam_grader.md` | `user/exam_grader_text.md` | `exam_grade_result.json` | `ExamGradeResult` | `grade_from_text` |
| `system/exam_grader.md` | `user/exam_grader_image.md` | `exam_grade_result.json` | `ExamGradeResult` | `grade_from_image` |
| `system/teach_it_back.md` | `user/teach_it_back.md` | `teach_it_back_result.json` | `TeachItBackResult` | `grade_teach_it_back` |

## Adding a new LLM function

1. Create `prompts/system/<name>.md` - write the system prompt; place `{schema}` where you want the response format and `{topic_material}` where you want optional topic context
2. Create `prompts/user/<name>.md` - write the user message template; use `{variable_name}` placeholders for the function's inputs
3. Create `schemas/<result_name>.json` - list every field the LLM must return, with a string description as the value
4. Add a Pydantic model in `bot/schemas.py` whose fields match the schema keys exactly; add it to the correspondence table above
5. In `bot/llm.py`, call `_load_prompt("system/<name>.md")` and `_load_prompt("user/<name>.md")` at module level, and `_load_schema("<result_name>")` for the schema
6. Implement the function: `_render(sys_template, schema=..., topic_material=...)` for the system prompt, `_render(user_template, ...)` for the user message, then `Model.model_validate(json.loads(...))` for parsing
7. Add tests in `tests/test_llm.py` covering: correct output, field population, system/user message content, topic_material injection, JSON parse failure, and OpenAI error fallback

## Editing an existing prompt

Edit the `.md` file directly. Templates are loaded once at module import - restart the process for changes to take effect in production.

Do not remove `{schema}` or `{topic_material}` from system templates - they are required by the loader.
