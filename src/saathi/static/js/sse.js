// @ts-check
// Server-Sent Events parser. EventSource cannot send an Authorization header, so the rooms UI reads
// the stream with fetch and feeds the decoded text here. Pure, so it runs under node --test.

/**
 * @typedef {{name: string, data: unknown}} SseEvent
 */

/**
 * Incremental parser: push text in arbitrary chunks, get whole events out. Comment lines (the
 * server's keepalives) are ignored. An event whose data is not valid JSON is dropped.
 * @param {(event: SseEvent) => void} onEvent
 * @returns {{push: (chunk: string) => void}}
 */
export function createSseParser(onEvent) {
  let buffer = "";
  let name = "message";
  /** @type {string[]} */
  let dataLines = [];

  function dispatch() {
    if (dataLines.length > 0) {
      try {
        onEvent({ name, data: JSON.parse(dataLines.join("\n")) });
      } catch {
        // Malformed payload: skip it rather than break the stream.
      }
    }
    name = "message";
    dataLines = [];
  }

  /** @param {string} line */
  function handleLine(line) {
    if (line === "") return dispatch();
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") name = value;
    else if (field === "data") dataLines.push(value);
  }

  return {
    push(chunk) {
      buffer += chunk;
      let match;
      while ((match = /\r\n|\n|\r/.exec(buffer))) {
        // A trailing lone CR may be the first half of CRLF; wait for more input.
        if (match[0] === "\r" && match.index === buffer.length - 1) return;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        handleLine(line);
      }
    },
  };
}
