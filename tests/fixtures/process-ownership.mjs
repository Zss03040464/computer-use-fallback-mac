export function commandMatchesOwnership(command, executable, requiredToken = null) {
  const executableMatches = command === executable || command.startsWith(`${executable} `);
  if (!executableMatches) return false;
  if (requiredToken === null) return true;
  const argumentsText = command.slice(executable.length).trim();
  return argumentsText.split(/\s+/).includes(requiredToken);
}


export function selectOwnedProcessIds(rows, executable, preexisting, requiredToken = null) {
  return rows
    .filter((row) => !preexisting.has(row.pid))
    .filter((row) => commandMatchesOwnership(row.command, executable, requiredToken))
    .map((row) => row.pid);
}


export function parseProcessRows(output) {
  const rows = [];
  for (const line of output.split('\n')) {
    const match = line.match(/^\s*(\d+)\s+(.*)$/);
    if (match) rows.push({ pid: Number(match[1]), command: match[2] });
  }
  return rows;
}
