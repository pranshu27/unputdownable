import React from 'react';
import { Typography } from '@mui/material';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext } from 'react-router-dom';

interface PlaceholderItem {
  title: string;
  copy: string;
  tone?: 'warning' | 'success' | 'neutral';
}

interface WorkspacePlaceholderProps {
  title: string;
  subtitle: string;
  sections: PlaceholderItem[];
  scoreLabel: string;
  scoreValue: string;
}

export default function WorkspacePlaceholder({
  title,
  subtitle,
  sections,
  scoreLabel,
  scoreValue,
}: WorkspacePlaceholderProps) {
  const { sideNavWidth } = useOutletContext<any>();

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
    >
      <div className="space-y-6">
        <FileWorkspaceHeader pageTitle={title} />
        <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-stone-950">{title}</h2>
              <p className="mt-2 text-sm text-stone-500">{subtitle}</p>
            </div>
            <div className="rounded-2xl border border-stone-200 bg-stone-50 px-5 py-4 text-right">
              <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">{scoreLabel}</p>
              <p className="mt-2 text-3xl font-semibold text-stone-950">{scoreValue}</p>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {sections.map((section) => (
            <div key={section.title} className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-base font-semibold text-stone-950">{section.title}</h3>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    section.tone === 'warning'
                      ? 'bg-amber-50 text-amber-700'
                      : section.tone === 'success'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-stone-100 text-stone-700'
                  }`}
                >
                  {section.tone === 'warning' ? 'Needs review' : section.tone === 'success' ? 'Pass' : 'Queued'}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-stone-500">{section.copy}</p>
              <div className="mt-5 rounded-xl border border-dashed border-stone-200 bg-stone-50 p-4 text-xs text-stone-500">
                Placeholder data region for backend response
              </div>
            </div>
          ))}
        </section>
      </div>
    </ContentCard>
  );
}
