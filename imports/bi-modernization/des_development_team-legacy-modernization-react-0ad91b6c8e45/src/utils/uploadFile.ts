
import { useMutation } from '@tanstack/react-query';

export const useUploadFile = () => {
  return useMutation({
    mutationFn: async ({ selectedFile, etlTool, model }) => {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('etltool', etlTool);
      formData.append('model', model);

      const response = await fetch('https://sdlc-autogen-default.apps.cfgclusternew.pg7v.p1.openshiftapps.com/upload/', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('Failed to upload');

      return response.json(); 
    },
  });
};
