import { useState } from 'react'

/** Copyable CLI command with accessible feedback. */
export default function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard unavailable (e.g. insecure context); user can select manually.
    }
  }

  return (
    <div className="copy-command">
      <code>{command}</code>
      <button type="button" onClick={copy} aria-live="polite">
        {copied ? 'Copied!' : 'Copy'}
      </button>
    </div>
  )
}