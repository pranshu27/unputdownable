import React from 'react';
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { cn } from '../../../Lib/utils.ts';

const steps = [
  { id: 1, name: 'Upload', description: 'Source file' },
  // { id: 2, name: 'Source', description: 'Platform' }, // Commented out - Auto-detected from file extension
  { id: 2, name: 'AI Model', description: 'Analysis' },
  { id: 3, name: 'Analyze', description: 'Execute' },
  // { id: 4, name: 'Framework', description: 'Processing' }, // Commented out - Framework selection hidden
];

export default function StepIndicator({ currentStep, completedSteps, onStepClick }) {
  return (
    <div className="w-full py-6">
      <div className="flex items-center justify-between relative">
        {/* Progress Line Background */}
        <div className="absolute top-5 left-0 right-0 h-[2px] bg-slate-200" />

        {/* Animated Progress Line */}
        <motion.div
          className="absolute top-5 left-0 h-[2px] bg-gradient-to-r from-red-700 to-red-900"
          initial={{ width: '0%' }}
          animate={{ width: `${((currentStep - 1) / (steps.length - 1)) * 100}%` }}
          transition={{ duration: 0.5, ease: 'easeInOut' }}
        />

        {steps.map((step, index) => {
          const isCompleted = completedSteps.includes(step.id);
          const isCurrent = currentStep === step.id;
          const isClickable = isCompleted || step.id <= Math.max(...completedSteps, 1) + 1;

          return (
            <motion.button
              key={step.id}
              onClick={() => isClickable && onStepClick(step.id)}
              disabled={!isClickable}
              className={cn(
                "relative z-10 flex flex-col items-center group",
                isClickable ? "cursor-pointer" : "cursor-not-allowed"
              )}
              whileHover={isClickable ? { scale: 1.05 } : {}}
              whileTap={isClickable ? { scale: 0.98 } : {}}
            >
              {/* Step Circle */}
              <motion.div
                className={cn(
                  "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 border-2",
                  isCompleted && "bg-gradient-to-br from-red-700 to-red-900 border-transparent text-white shadow-lg shadow-red-500/20",
                  isCurrent && !isCompleted && "bg-white border-red-700 text-red-700 shadow-lg shadow-red-500/10",
                  !isCompleted && !isCurrent && "bg-white border-slate-200 text-slate-400"
                )}
                animate={isCurrent ? {
                  boxShadow: ['0 0 0 0 rgba(200, 16, 46, 0.28)', '0 0 0 8px rgba(200, 16, 46, 0)', '0 0 0 0 rgba(200, 16, 46, 0)']
                } : {}}
                transition={isCurrent ? { duration: 2, repeat: Infinity } : {}}
              >
                {isCompleted ? (
                  <Check className="w-5 h-5" strokeWidth={2.5} />
                ) : (
                  <span className={cn("text-sm font-semibold", isCurrent ? "text-red-700" : "text-[#94A3B8]")}>{step.id}</span>)}
              </motion.div>

              {/* Step Label */}
              <div className="mt-3 text-center">
                <p className={cn(
                  "text-sm font-medium transition-colors",
                  isCurrent ? "text-red-700" : isCompleted ? "text-stone-700" : "text-stone-400"
                )}>
                  {step.name}
                </p>
                <p className={cn(
                  "text-xs transition-colors",
                  isCurrent ? "text-red-700" : "text-stone-400"
                )}>
                  {step.description}
                </p>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
