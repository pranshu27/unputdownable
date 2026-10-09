import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Zap, Brain, Sparkles, ChevronDown, Info } from 'lucide-react';
import { cn } from '../../../Lib/utils.ts';
import GPT from '../../../Assets/openAi.svg';
import claude from '../../../Assets/claude.png';
import Gemini from '../../../Assets/gemini.svg';
import AWS from '../../../Assets/aws.svg';

export const modelVersions = {
  'openai': [
    { id: 'gpt-5 mini', label: 'GPT-5 Mini' },
    { id: 'gpt-4o', label: 'GPT-4o' },
    { id: 'gpt-4o-mini', label: 'GPT-4o Mini' },
    { id: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
    { id: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
    { id: 'o1-preview', label: 'o1 Preview' },
    { id: 'o1-mini', label: 'o1 Mini' },
  ],
  'gemini': [
    { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
    { id: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
    { id: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    { id: 'gemini-1.0-pro', label: 'Gemini 1.0 Pro' },
    { id: 'gemini-ultra', label: 'Gemini Ultra' },
  ],
  'bedrock': [
    { id: 'claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
    { id: 'claude-3-haiku', label: 'Claude 3 Haiku' },
    { id: 'llama-3.1-70b', label: 'Llama 3.1 70B' },
    { id: 'mistral-large', label: 'Mistral Large' },
    { id: 'titan-text-g1', label: 'Titan Text G1' },
  ],
};

export const models = [
  {
    id: 'openai',
    name: 'GPT',
    provider: 'OpenAI',
    description: 'Most capable model for complex transformations',
    speed: 'Medium',
    accuracy: 'Highest',
    cost: '$$$',
    icon: GPT,
    color: 'emerald',
    gradient: 'from-emerald-500 to-green-600',
    bgGradient: 'from-emerald-50 to-green-50',
    recommended: true,
    defaultVersion: 'gpt-5 mini',
    capabilities: ['Complex Logic', 'Multi-step Reasoning', 'Code Generation'],
  },
  {
    id: 'gemini',
    name: 'Gemini Pro',
    provider: 'Google',
    description: 'Excellent for large-scale data processing',
    speed: 'Fast',
    accuracy: 'High',
    cost: '$$',
    icon: Gemini,
    color: 'blue',
    gradient: 'from-blue-500 to-indigo-600',
    bgGradient: 'from-blue-50 to-indigo-50',
    defaultVersion: 'gemini-1.5-pro',
    capabilities: ['Large Context', 'Multimodal', 'Fast Processing'],
  },
  {
    id: 'bedrock',
    name: 'AWS Bedrock',
    provider: 'Amazon',
    description: 'Enterprise-grade AI with multiple model options',
    speed: 'Fast',
    accuracy: 'High',
    cost: '$$',
    icon: AWS,
    color: 'orange',
    gradient: 'from-orange-500 to-amber-600',
    bgGradient: 'from-orange-50 to-amber-50',
    defaultVersion: 'claude-3-haiku',
    capabilities: ['Enterprise Security', 'Model Choice', 'Scalable Infrastructure'],
  },
];

const speedColors = {
  'Fast': 'text-green-600 bg-green-50',
  'Medium': 'text-amber-600 bg-amber-50',
  'Slow': 'text-red-600 bg-red-50',
};

const accuracyColors = {
  'Highest': 'text-emerald-600 bg-emerald-50',
  'High': 'text-blue-600 bg-blue-50',
  'Medium': 'text-amber-600 bg-amber-50',
};

export default function AIModelSelector({ selected, onSelect }) {
  const [showDetails, setShowDetails] = useState(null);

  // Track selected version per provider, defaulting to each model's defaultVersion
  const [selectedVersions, setSelectedVersions] = useState(() =>
    Object.fromEntries(models.map(m => [m.id, m.defaultVersion]))
  );

  const handleVersionChange = (e, modelId) => {
    e.stopPropagation();
    const newVersions = { ...selectedVersions, [modelId]: e.target.value };
    setSelectedVersions(newVersions);

    // If this provider card is already selected, update parent with new version label
    if (selected?.id === modelId) {
      const model = models.find(m => m.id === modelId);
      const versionLabel = modelVersions[modelId].find(v => v.id === e.target.value)?.label;
      onSelect({ ...model, selectedVersion: e.target.value, selectedVersionLabel: versionLabel });
    }
  };

  const handleCardSelect = (model) => {
    const versionLabel = modelVersions[model.id].find(v => v.id === selectedVersions[model.id])?.label;
    onSelect({ ...model, selectedVersion: selectedVersions[model.id], selectedVersionLabel: versionLabel });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Select AI Model</h2>
        <p className="text-sm text-slate-500 mt-1">
          Choose the AI model that powers your transformation
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {models.map((model, idx) => (
          <motion.div
            key={model.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.1 }}
            className="relative"
          >
            <motion.button
              onClick={() => handleCardSelect(model)}
              whileHover={{ scale: 1.02, y: -4 }}
              whileTap={{ scale: 0.98 }}
              className={cn(
                "w-full p-5 rounded-2xl border-2 text-left transition-all duration-300 relative overflow-hidden",
                selected?.id === model.id
                  ? `bg-gradient-to-br ${model.bgGradient} border-transparent shadow-xl`
                  : "bg-white border-slate-200 hover:border-slate-300 hover:shadow-lg opacity-50"
              )}
            >
              {/* Recommended Badge
              {model.recommended && (
                <div className="absolute -top-1 -right-1">
                  <div className="bg-gradient-to-r from-amber-400 to-orange-500 text-white text-[10px] font-bold px-2 py-1 rounded-bl-lg rounded-tr-xl shadow-lg">
                    BEST
                  </div>
                </div>
              )} */}

              {/* Selection Check */}
              {selected?.id === model.id && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className={cn(
                    "absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center",
                    `bg-gradient-to-br ${model.gradient}`
                  )}
                >
                  <Check className="w-3.5 h-3.5 text-white" />
                </motion.div>
              )}

              <div className="space-y-4">
                {/* Header */}
                <div className="flex items-start gap-3">
                  <img
                    src={model.icon}
                    alt={model.name}
                    className={cn(
                      "w-12 h-12 rounded-xl flex items-center justify-center text-2xl shadow-lg",
                      `bg-gradient-to-br ${model.gradient}`
                    )}
                  />
                  <div>
                    <h3 className="font-semibold text-slate-800">{model.name}</h3>
                    <p className="text-xs text-slate-500">{model.provider}</p>
                  </div>
                </div>

                {/* Description */}
                <p className="text-sm text-slate-600 leading-relaxed">
                  {model.description}
                </p>

                {/* Model Version Dropdown */}
                <div
                  className="relative"
                  onClick={e => e.stopPropagation()}
                >
                  <select
                    value={selectedVersions[model.id]}
                    onChange={e => handleVersionChange(e, model.id)}
                    className={cn(
                      "w-full appearance-none text-xs rounded-lg px-3 py-2 pr-7 border cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1",
                      selected?.id === model.id
                        ? "bg-white/70 border-white/50 text-slate-700 focus:ring-white/50"
                        : "bg-slate-50 border-slate-200 text-slate-600 hover:border-slate-300 focus:ring-slate-300"
                    )}
                  >
                    {modelVersions[model.id].map(version => (
                      <option key={version.id} value={version.id}>
                        {version.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                </div>

                {/* Expand Button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowDetails(showDetails === model.id ? null : model.id);
                  }}
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 transition-colors"
                >
                  <Info className="w-3.5 h-3.5" />
                  <span className="text-slate-800">View capabilities</span>
                  <ChevronDown className={cn(
                    "w-3.5 h-3.5 transition-transform",
                    showDetails === model.id && "rotate-180"
                  )} />
                </button>

                {/* Capabilities */}
                <AnimatePresence>
                  {showDetails === model.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="pt-2 space-y-2">
                        {model.capabilities.map(cap => (
                          <div key={cap} className="flex items-center gap-2 text-sm text-slate-600">
                            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                            {cap}
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.button>
          </motion.div>
        ))}
      </div>
    </div>
  );
}