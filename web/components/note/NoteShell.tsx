'use client'

import { useState, type ReactNode } from 'react'

/** Client boundary for the research note: owns only the language state.
 *  All content is server-rendered children (both languages in the DOM;
 *  CSS shows one based on data-lang). */
export default function NoteShell({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<'en' | 'zh'>('en')
  return (
    <div className="note-root" data-lang={lang}>
      <div className="sheet">
        <div className="langbar">
          <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')}>
            EN
          </button>
          <button className={lang === 'zh' ? 'on' : ''} onClick={() => setLang('zh')}>
            中文
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
