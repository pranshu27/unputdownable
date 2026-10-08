import React from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import './TileSelector.scss';

interface TileSelectorProps {
  title: string;
  items: Array<{
    key: string;
    value: string;
    icon: string;
    description?: string;
    disabled?: boolean;
  }>;
  selectedValue: string | string[];
  onChange: (value: string) => void;
  multiSelect?: boolean;
  stepNumber?: number;
}

const TileSelector: React.FC<TileSelectorProps> = ({
  title,
  items,
  selectedValue,
  onChange,
  multiSelect = false,
  stepNumber
}) => {
  const isSelected = (value: string) => {
    if (Array.isArray(selectedValue)) {
      return selectedValue.includes(value);
    }
    return selectedValue === value;
  };

  return (
    <Box className="tile-selector-container">
      <Box className="tile-selector-header">
        {stepNumber && (
          <Box className="step-badge">
            <span className="step-number">{stepNumber}</span>
          </Box>
        )}
        <Typography variant="h6" className="tile-selector-title">
          {title}
        </Typography>
      </Box>

      <Box className="tiles-grid">
        {items.map((item) => {
          const selected = isSelected(item.value);

          return (
            <Tooltip
              key={item.value}
              title={item.disabled ? "Not available for this selection" : (item.description || item.key)}
              placement="top"
              arrow
              classes={{ tooltip: 'custom-tooltip' }}
            >
              <Box
                className={[
                  "tile-item",
                  selected ? "selected" : "",
                  item.disabled ? "disabled" : "",
                ].join(" ").trim()}
                onClick={() => {
                  if (!item.disabled) {
                    onChange(item.value);
                  }
                }}
              >
                {/* Selected tick */}
                {selected && !item.disabled && (
                  <Box className="selection-indicator">
                    <CheckCircleIcon className="check-icon" />
                  </Box>
                )}

                <Box className="tile-icon-wrapper">
                  <img src={item.icon} alt={item.key} className="tile-icon" />
                  <Box className="icon-glow" />
                </Box>

                <Typography className="tile-label">
                  {item.key}
                </Typography>

                <Box className="tile-shine" />
              </Box>
            </Tooltip>
          );
        })}
      </Box>

      {multiSelect && (
        <Typography className="multi-select-hint">
          💡 You can select multiple options
        </Typography>
      )}
    </Box>
  );
};

export default TileSelector;
