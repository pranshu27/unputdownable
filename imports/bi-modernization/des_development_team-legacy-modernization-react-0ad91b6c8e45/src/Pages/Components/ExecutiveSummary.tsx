import { useMemo, useState } from 'react';
import { DataModel } from '../../data/sampleModel';
import { ChevronDown, ChevronRight, FileText } from 'lucide-react';
import { cn } from "../../Lib/utils.ts";
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext } from 'react-router-dom';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
interface Props {
  model: DataModel;
}

interface Section {
  title: string;
  body: string[];
}

function parseSummary(raw: string): Section[] {
  const lines = raw.split('\n');
  const sections: Section[] = [];
  let current: Section | null = null;

  const isHeading = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return false;
    if (trimmed.startsWith('-') || trimmed.startsWith('•')) return false;
    if (trimmed.length > 90) return false;
    const hasEndingPunctuation = /[.!?,:;]$/.test(trimmed);
    const startsUpper = /^[A-Z]/.test(trimmed);
    return startsUpper && !hasEndingPunctuation;
  };

  for (const line of lines) {
    if (isHeading(line) && line.trim().length < 80) {
      if (current) sections.push(current);
      current = { title: line.trim(), body: [] };
    } else {
      if (!current) current = { title: 'Summary', body: [] };
      current.body.push(line);
    }
  }
  if (current) sections.push(current);
  return sections.filter((s) => s.body.some((l) => l.trim().length > 0));
}

function renderBody(body: string[]) {
  const blocks: { type: 'p' | 'ul'; items: string[] }[] = [];
  let currentList: string[] = [];
  let currentPara: string[] = [];

  const flushList = () => {
    if (currentList.length) {
      blocks.push({ type: 'ul', items: [...currentList] });
      currentList = [];
    }
  };
  const flushPara = () => {
    if (currentPara.length) {
      const text = currentPara.join(' ').trim();
      if (text) blocks.push({ type: 'p', items: [text] });
      currentPara = [];
    }
  };

  for (const line of body) {
    const t = line.trim();
    if (!t) {
      flushPara();
      flushList();
      continue;
    }
    if (t.startsWith('-') || t.startsWith('•')) {
      flushPara();
      currentList.push(t.replace(/^[-•]\s*/, ''));
    } else {
      flushList();
      currentPara.push(t);
    }
  }
  flushPara();
  flushList();

  return blocks;
}

export default function ExecutiveSummary({ model }: Props) {
  const sections = useMemo(() => parseSummary(model.technical_summary), [model.technical_summary]);
  const [open, setOpen] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(sections.map((_, i) => [i, i < 3]))
  );
  const { sideNavWidth } = useOutletContext();

    return (
    <ContentCard
    heading={null}
      sideNavWidth={sideNavWidth}
   >
    <div className="space-y-8">
      <FileWorkspaceHeader pageTitle="Summary" />
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setOpen(Object.fromEntries(sections.map((_, i) => [i, true])))}
          className="text-[12.5px] px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-all duration-200 font-semibold shadow-sm"
        >
          Expand all
        </button>
        <button
          onClick={() => setOpen(Object.fromEntries(sections.map((_, i) => [i, false])))}
          className="text-[12.5px] px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-all duration-200 font-semibold shadow-sm"
        >
          Collapse all
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6 space-y-4">
        {sections.map((section, idx) => {
          const isOpen = open[idx] ?? false;
          const blocks = renderBody(section.body);
          return (
            <div
              key={idx}
              className={cn(
                'rounded-2xl border overflow-hidden transition-all duration-200 shadow-sm',
                isOpen ? 'border-slate-300 bg-white shadow-md' : 'border-slate-200/70 bg-white hover:border-slate-300 hover:shadow-md'
              )}
            >
              <button
                onClick={() => setOpen((s) => ({ ...s, [idx]: !isOpen }))}
                className="w-full px-6 py-5 flex items-center gap-3 text-left hover:bg-slate-50/60 transition-colors"
              >
                <div className="w-8 h-8 rounded-lg bg-indigo-50 ring-4 ring-indigo-50/50 flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4 text-indigo-600" strokeWidth={2.2} />
                </div>
                <h3 className="text-[15px] font-semibold text-slate-900 flex-1">{section.title}</h3>
                {isOpen ? (
                  <ChevronDown className="w-[18px] h-[18px] text-slate-400" />
                ) : (
                  <ChevronRight className="w-[18px] h-[18px] text-slate-400" />
                )}
              </button>
              {isOpen && (
                <div className="px-7 pb-6 pt-2 border-t border-slate-100 space-y-4">
                  {blocks.map((b, i) =>
                    b.type === 'p' ? (
                      <p key={i} className="text-[14px] text-slate-700 leading-[1.75]">
                        {b.items[0]}
                      </p>
                    ) : (
                      <ul key={i} className="space-y-2">
                        {b.items.map((item, j) => (
                          <li key={j} className="text-[14px] text-slate-600 leading-[1.7] flex gap-3">
                            <span className="mt-[9px] w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
                            <span className="text-slate-600">{item}</span>
                          </li>
                        ))}
                      </ul>
                    )
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  </ContentCard>

  );
}
