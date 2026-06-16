# Font Converter Design

## Goal

Build a deployable web tool that lets users upload a `.ttf` file, scale the font by percentage, choose Thin or Bold glyph conversion with user-controlled horizontal and vertical effect values, and download the converted `.ttf` from a visible download button.

## Architecture

Use a FastAPI server with a small static frontend. The browser uploads the font through a multipart request. The server validates the input, converts the font in memory using `fontTools`, and returns the converted bytes directly to the browser.

## Components

- `font_processor.py`: Pure font conversion logic. It validates scale and glyph effect settings, modifies glyph outlines and metrics, and returns converted bytes.
- `main.py`: FastAPI app. It serves the frontend, validates uploads, calls the converter, and returns the converted font with an automatic download filename.
- `templates/index.html`: User interface for upload, scale percentage, Thin/Bold effect controls, manual download button, and download status.
- `static/styles.css`: Layout and visual styling.
- `static/app.js`: Frontend form handling and file download behavior.
- `tests/`: Automated tests for conversion behavior and API validation.

## Data Flow

1. User opens the web page.
2. User selects a `.ttf` file and conversion options.
3. Browser uploads the file and options to `/api/convert`.
4. Server keeps the upload only in request-scoped memory.
5. `fontTools` converts the uploaded font.
6. Server returns the converted `.ttf` as an attachment.
7. Browser stores the response as a local blob and reveals a download button.
8. Server releases the request data after the response completes.

## Conversion Behavior

Scaling changes glyph outlines and common font metrics by the requested percentage while preserving the original units per em. Glyph effect processing supports `none`, `thin`, and `bold` modes. Thin and Bold use user-supplied horizontal and vertical effect percentages, converted to font units from `unitsPerEm`.

Valid scale range is 10% to 300%. Horizontal and vertical effect values are controlled by the user and validated to a bounded range so extreme values do not produce invalid fonts. The output filename is generated as `original-scalePct-effect.ttf`, including Thin/Bold horizontal and vertical effect values when relevant.

## Error Handling

The server rejects missing files, non-`.ttf` filenames, empty uploads, invalid scale values, invalid glyph effect values, unsafe output names, and conversion failures. The frontend shows the returned error message and keeps the page usable for another attempt.

## Deployment

The app can run behind Nginx with Uvicorn or Gunicorn/Uvicorn workers. Upload size should be limited by the reverse proxy and app configuration. The server does not retain uploaded fonts after processing.

## Testing

Tests cover conversion validation, generated TTF readability, scaling effects on metrics, Thin/Bold conversion, output filename handling, and API input errors.
