import React from 'react';
import { motion } from 'framer-motion';
import { Check, Cpu, GitBranch, Workflow, Sparkles } from 'lucide-react';
import { cn } from '../../../Lib/utils.ts';

export const frameworks = [
  {
    id: 'multiagent',
    name: 'Multi-Agent MAS',
    description: 'Distributed processing with multiple specialized agents working in parallel',
    icon: Cpu,
    features: ['Parallel Processing', 'Self-Healing', 'Scalable'],
    gradient: 'from-violet-500 to-purple-600',
    bgGradient: 'from-violet-50 to-purple-50',
    recommended: true,
  },
  // {
  //   id: 'promptorchestration',
  //   name: 'Prompt Orchestration',
  //   description: 'Sequential prompt chains with optimized token management',
  //   icon: Workflow,
  //   features: ['Token Efficient', 'Deterministic', 'Debuggable'],
  //   gradient: 'from-blue-500 to-cyan-600',
  //   bgGradient: 'from-blue-50 to-cyan-50',
  // }
];

export default function FrameworkSelector({ selected, onSelect }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Select Framework</h2>
        <p className="text-sm text-slate-500 mt-1">
          Choose the processing framework for your transformation
        </p>
      </div>

      <div className="grid gap-4">
        {frameworks.map((framework, idx) => (
          <motion.button
            key={framework.id}
            onClick={() => onSelect(framework)}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.1 }}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className={cn(
              "relative w-full p-6 rounded-2xl border-2 text-left transition-all duration-300 overflow-hidden",
              selected?.id === framework.id
                ? `bg-gradient-to-br ${framework.bgGradient} border-transparent shadow-xl`
                : "bg-white border-slate-200 hover:border-slate-300 hover:shadow-lg"
            )}
          >
            {/* Background Pattern */}
            <div className="absolute inset-0 opacity-5">
              <div className="absolute inset-0" style={{
                backgroundImage: 'radial-gradient(circle at 2px 2px, currentColor 1px, transparent 0)',
                backgroundSize: '24px 24px'
              }} />
            </div>

            {/* Recommended Badge */}
            {framework.recommended && (
              <div className="absolute top-4 right-4">
                <span className="flex items-center gap-1 px-2.5 py-1 bg-gradient-to-r from-amber-400 to-orange-500 text-white text-xs font-semibold rounded-full shadow-lg">
                  <Sparkles className="w-3 h-3" />
                  Recommended
                </span>
              </div>
            )}

            {/* Selection Indicator */}
            {selected?.id === framework.id && (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className={cn(
                  "absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center",
                  `bg-gradient-to-br ${framework.gradient} shadow-lg`
                )}
              >
                <Check className="w-4 h-4 text-white" />
              </motion.div>
            )}

            <div className="relative flex items-start gap-5">
              {/* Icon */}
              <div className={cn(
                "flex-shrink-0 w-14 h-14 rounded-xl flex items-center justify-center shadow-lg",
                `bg-gradient-to-br ${framework.gradient}`
              )}>
                <framework.icon className="w-7 h-7 text-white" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <h3 className={cn(
                  "text-lg font-semibold",
                  selected?.id === framework.id ? "text-slate-800" : "text-slate-800"
                )}>
                  {framework.name}
                </h3>
                <p className="text-sm text-slate-600 mt-1 leading-relaxed">
                  {framework.description}
                </p>
                
                {/* Feature Tags */}
                <div className="flex flex-wrap gap-2 mt-4">
                  {framework.features.map(feature => (
                    <span 
                      key={feature}
                      className={cn(
                        "px-3 py-1 rounded-full text-xs font-medium",
                        selected?.id === framework.id
                          ? "bg-white/70 text-slate-700"
                          : "bg-slate-100 text-slate-600"
                      )}
                    >
                      {feature}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Active State Glow */}
            {selected?.id === framework.id && (
              <motion.div
                className={cn(
                  "absolute inset-0 rounded-2xl opacity-20",
                  `bg-gradient-to-br ${framework.gradient}`
                )}
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.1 }}
              />
            )}
          </motion.button>
        ))}
      </div>
    </div>
  );
}