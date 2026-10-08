import React from 'react';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store';
import Lineage from './Lineage.tsx';
import LineageJNJ from './LineageJNJ.tsx';
import { ReactFlowProvider } from '@xyflow/react';

const LineageWrapper = () => {
  const selectedCase = localStorage.getItem("selectedCase") || "jnj";
    console.log('case',selectedCase)
  return (
    <ReactFlowProvider>
      {selectedCase === 'jnj' ? <LineageJNJ /> : <Lineage />}
    </ReactFlowProvider>
  );
};

export default LineageWrapper;