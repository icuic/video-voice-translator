import axios from 'axios';

// 在开发环境下使用相对路径（通过 Vite proxy），生产环境使用环境变量或相对路径
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',  // 使用相对路径，通过 Vite proxy
  timeout: 300000,  // 增加超时时间，因为文件上传可能需要较长时间
});

// 添加请求拦截器，用于调试
api.interceptors.request.use(
  (config) => {
    console.log('API Request:', config.method?.toUpperCase(), config.url);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// 添加响应拦截器，用于错误处理
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Response Error:', error.response?.status, error.response?.data);
    return Promise.reject(error);
  }
);

export default api;


