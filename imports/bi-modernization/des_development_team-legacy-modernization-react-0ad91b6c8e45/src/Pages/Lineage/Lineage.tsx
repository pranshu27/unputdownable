import React from "react";
import "@xyflow/react/dist/style.css";
import NodeLineage from "./NodeLineage.tsx";
import { useSelector } from "react-redux";
import { RootState } from "../../utils/Store.ts";
import "./Lineage.scss";

// Remove ReactFlowProvider wrapper - it's now in LineageWrapper
const Lineage = () => {
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;

  return <NodeLineage />;
};

export default Lineage;