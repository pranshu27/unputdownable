import yaml from 'js-yaml';

export async function loadConfig() {
  try {
    const response = await fetch('/config.yaml');
    if (!response.ok) {
      return null;
    }

    const text = await response.text();
    const config = yaml.load(text);
    return config;
  } catch (error) {
    return null;
  }
}
