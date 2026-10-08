import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Check, ChevronRight, Database, Cloud, Server, Layers, X, BarChart3, Code2 } from 'lucide-react';
import { Input } from '../../CodeGen/CodeGenComponents/input.tsx';
import { cn } from '../../../Lib/utils.ts';
import AlteryxIcon from '../../../Assets/Alteryx.png';
import SSISIcon from '../../../Assets/ssis.png';
import BigQueryIcon from '../../../Assets/Bigquerylogo1.png';
import PowerBiIcon from '../../../Assets/powerbi.png';
import DbtIcon from '../../../Assets/DBT.png';
import PysparkIcon from '../../../Assets/Py Spark Logo 1.png';
import DataiquIcon from '../../../Assets/dataiq.png';
import xpierLogo from '../../../Assets/xpier-logo.svg';
import { setSelectedCase } from "../../../utils/selectedCaseSlice.ts";
import InformaticaIcon from '../../../Assets/Group4.png';
import QlickViewIcon from '../../../Assets/OSK 2.png';
import DataStageIcon from '../../../Assets/Group.png';
import MultiAgent from '../../../Assets/mutiagent.png';
import PromptAgent from '../../../Assets/prompt.png';
import TalendIcon from '../../../Assets/Talend.png';
import TableautIcon from '../../../Assets/tableau-icon.svg';
import WebfocusIcon from '../../../Assets/webfocus.svg';
import DataBricks from '../../../Assets/databricks.svg';
import Teradata from '../../../Assets/teradata.svg';
import SqlIcon from '../../../Assets/sql.svg';
import GPT from '../../../Assets/openAi.svg';
import Gemini from '../../../Assets/gemini.svg';
import SasIcon from '../../../Assets/sas.svg';
import PythonIcon from '../../../Assets/python.svg';
import CodeIcon from '@mui/icons-material/Code';
import SpringBoot from '../../../Assets/spring-boot-icon.svg';

import AnalyticsIcon from '@mui/icons-material/Analytics';
const platformCategories = {
  source: [
    {
      category: 'Data Re-Engineering',
      icon: Database,
      platforms: [
        { id: 'teradata', name: 'BTEQ', fullName: 'Teradata BTEQ scripting tool', icon: Teradata },
        { id: 'altreyx', name: 'Alteryx', fullName: 'Alteryx Designer', icon: AlteryxIcon, popular: true },
        { id: 'teradatasql', name: 'SQL', fullName: 'Teradata SQL queries', icon: SqlIcon },
        // { id: 'powercenter', name: 'Power Center', fullName: 'Informatica PowerCenter ETL', icon: InformaticaIcon, popular: true },
        { id: 'talend', name: 'Talend', fullName: 'Talend Open Studio', icon: TalendIcon, popular: true },
        { id: 'ssis', name: 'SSIS', fullName: 'SQL Server Integration', icon: SSISIcon },
        { id: 'informatica', name: 'Informatica', fullName: 'Informatica PowerCenter', icon: InformaticaIcon },
        { id: 'datastage', name: 'DataStage', fullName: 'IBM DataStage', icon: DataStageIcon },
        { id: 'iics', name: 'IICS', fullName: 'Informatica Cloud', icon: InformaticaIcon },
      ]
    },
    {
      category: 'BI & Analytics Re-Engineering',
      icon: BarChart3,
      platforms: [
        { id: 'tableau-workbook', name: 'Tableau', fullName: 'Tableau Workbook', icon: TableautIcon , popular: true},
        { id: 'webfocus', name: 'Webfocus', fullName: 'WebFocus', icon: WebfocusIcon },
        { id: 'qlikview', name: 'QlikView', fullName: 'QlikView BI platform', icon: QlickViewIcon },
        {
          id: 'powerbi',
          name: 'Power BI',
          fullName: 'Microsoft Power BI',
          icon: PowerBiIcon,
          popular: true
        },
        { 
          id: 'qlik', 
          name: 'Qlik Sense', 
          fullName: 'Qlik Sense Analytics Platform', 
          icon: QlickViewIcon,
          popular: true 
        },
      ]
    },
    {
      category: 'Application Re-Engineering',
      icon: Code2,
      platforms: [
        { id: 'sas', name: 'SAS', fullName: 'SAS Data Management', icon: SasIcon, popular: true },
        { id: 'IBM COBOL', name: 'IBM COBOL', fullName: 'COBOL Programming Language', icon: DataStageIcon },
      ]
    },
  ],
  target: [
    {
      category: 'Modern Frameworks',
      icon: Layers,
      platforms: [
        { id: 'dbt', name: 'dbt', fullName: 'Data Build Tool', icon: DbtIcon, popular: true },
        { id: 'pyspark', name: 'PySpark', fullName: 'PySpark DataFrame', icon: PysparkIcon, popular: true },
        { id: 'bigquery', name: 'BigQuery', fullName: 'BigQuery Analytics', icon: BigQueryIcon, popular: true },

      ]
    },
    
    {
      category: 'Python Ecosystem',
      icon: Database,
      platforms: [
        { id: 'python', name: 'Python', fullName: 'Python Pandas', icon: PythonIcon, popular: true },
      ]
    },
  ]
};

export default function PlatformSelector({ type, selected, onSelect, title, subtitle }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCategory, setExpandedCategory] = useState(null);
  const [hoveredPlatform, setHoveredPlatform] = useState(null);

  const categories = platformCategories[type] || [];

  const allPlatforms = categories.flatMap(cat => cat.platforms);
  const filteredPlatforms = searchQuery
    ? allPlatforms.filter(p =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.fullName.toLowerCase().includes(searchQuery.toLowerCase())
    )
    : null;

  const popularPlatforms = allPlatforms.filter(p => p.popular);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-800">{title}</h2>
          <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
        </div>
        {selected && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center gap-2 px-4 py-2 bg-red-50 rounded-lg border border-red-100"
          >
            {/* <span className="text-2xl">{selected.icon}</span> */}
            <img src={selected.icon} alt={selected.name} className="w-6 h-6" />
            <div>
              <p className="text-sm font-medium text-red-900">{selected.name}</p>
              <p className="text-xs text-red-700">Selected</p>
            </div>
            <button
              onClick={() => onSelect(null)}
              className="ml-2 p-1 hover:bg-red-100 rounded-lg transition-colors"
            >
              <X className="w-4 h-4 text-red-700" />
            </button>
          </motion.div>
        )}
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search platforms..."
          className="pl-12 h-12 bg-stone-50 border-stone-200 rounded-lg focus:bg-white transition-colors"
        />
      </div>

      {/* Quick Select - Popular Platforms */}
      {!searchQuery && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Popular Choices</p>
          <div className="flex flex-wrap gap-2">
            {popularPlatforms.map(platform => (
              <motion.button
                key={platform.id}
                onClick={() => onSelect(platform)}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className={cn(
                  "flex items-center gap-2 px-4 py-2.5 rounded-lg border-2 transition-all duration-200",
                  selected?.id === platform.id
                    ? "bg-red-50 border-red-600 shadow-lg shadow-red-500/10"
                    : "bg-white border-stone-200 hover:border-red-300 hover:shadow-md"
                )}
              >
                <img src={platform.icon} alt={platform.name} className="w-6 h-6" />
                <span className={cn(
                  "font-medium",
                  selected?.id === platform.id ? "text-red-900" : "text-stone-700"
                )}>
                  {platform.name}
                </span>
                {selected?.id === platform.id && (
                  <Check className="w-4 h-4 text-red-700" />
                )}
              </motion.button>
            ))}
          </div>
        </div>
      )}

      {/* Search Results */}
      {searchQuery && filteredPlatforms && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-2 md:grid-cols-3 gap-3"
        >
          {filteredPlatforms.length > 0 ? (
            filteredPlatforms.map(platform => (
              <PlatformCard
                key={platform.id}
                platform={platform}
                isSelected={selected?.id === platform.id}
                onSelect={() => onSelect(platform)}
              />
            ))
          ) : (
            <div className="col-span-full py-8 text-center text-slate-500">
              No platforms found matching "{searchQuery}"
            </div>
          )}
        </motion.div>
      )}

      {/* Category Browser */}
      {!searchQuery && (
        <div className="space-y-4">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">All Platforms</p>
          <div className="space-y-3">
            {categories.map((category, idx) => (
              <motion.div
                key={category.category}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="border border-stone-200 rounded-lg overflow-hidden bg-white"
              >
                <button
                  onClick={() => setExpandedCategory(
                    expandedCategory === category.category ? null : category.category
                  )}
                  className="w-full flex items-center justify-between p-4 hover:bg-stone-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-red-50 to-stone-100 flex items-center justify-center">
                      <category.icon className="w-5 h-5 text-red-700" />
                    </div>
                    <div className="text-left">
                      <p className="font-medium text-stone-900">{category.category}</p>
                      <p className="text-sm text-stone-500">{category.platforms.length} platforms</p>
                    </div>
                  </div>
                  <ChevronRight className={cn(
                    "w-5 h-5 text-slate-400 transition-transform duration-200",
                    expandedCategory === category.category && "rotate-90"
                  )} />
                </button>

                <AnimatePresence>
                  {expandedCategory === category.category && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="p-4 pt-0 grid grid-cols-2 md:grid-cols-3 gap-3">
                        {category.platforms.map(platform => (
                          <PlatformCard
                            key={platform.id}
                            platform={platform}
                            isSelected={selected?.id === platform.id}
                            onSelect={() => onSelect(platform)}
                            isHovered={hoveredPlatform === platform.id}
                            onHover={setHoveredPlatform}
                          />
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
function PlatformCard({ platform, isSelected, onSelect, isHovered, onHover }) {
  return (
    <motion.button
      onClick={onSelect}
      onMouseEnter={() => onHover?.(platform.id)}
      onMouseLeave={() => onHover?.(null)}
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      className={cn(
        "relative px-5 py-3 rounded-lg border-2 transition-all duration-200 text-left group",
        isSelected
          ? "bg-gradient-to-br from-red-50 to-stone-50 border-red-600 shadow-lg shadow-red-500/10"
          : "bg-white border-stone-200 hover:border-red-300 hover:shadow-md"
      )}
    >
      <div className="flex items-center justify-between gap-3">
        {/* Icon and Name side by side */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <img
            src={platform.icon}
            alt={platform.name}
            className="w-7 h-7 flex-shrink-0"
          />
          <p className={cn(
            "font-semibold text-base truncate",
            isSelected ? "text-red-900" : "text-stone-900"
          )}>
            {platform.name}
          </p>
        </div>

        {/* Checkmark */}
        {isSelected && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="w-5 h-5 rounded-full bg-red-700 flex items-center justify-center flex-shrink-0"
          >
            <Check className="w-3 h-3 text-white" />
          </motion.div>
        )}
      </div>
    </motion.button>
  );
}
