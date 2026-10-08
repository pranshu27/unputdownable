// useApiWithLoader.js
import { useState } from "react";
import axios from "axios";

export const useApiWithLoader = () => {
  const [loading, setLoading] = useState(false);

  const callApi = async (config) => {
    try {
      setLoading(true);
      const response = await axios(config);
      return response.data;
    } finally {
    setTimeout(() => {
 setLoading(false);
    },3000)
     
    }
  };

  return { callApi, loading };
};
