const replacements: Array<[string, string]> = [
  ['任务已创建，等待处理...', 'Task created, waiting to start...'],
  ['正在启动翻译任务...', 'Starting translation task...'],
  ['初始化中...', 'Initializing...'],
  ['翻译完成', 'Translation completed'],
  ['处理中...', 'Processing...'],
  ['已完成', 'Completed'],
  ['处理中', 'Processing'],
  ['等待中', 'Pending'],
  ['失败', 'Failed'],
  ['待编辑分段', 'Awaiting segment review'],
  ['待编辑翻译', 'Awaiting translation review'],
  ['音频提取', 'Audio extraction'],
  ['人声分离', 'Vocal separation'],
  ['多说话人处理', 'Speaker diarization'],
  ['语音识别', 'Speech recognition'],
  ['文本翻译', 'Text translation'],
  ['参考音频提取', 'Reference audio extraction'],
  ['音色克隆', 'Voice cloning'],
  ['音频合并', 'Audio merging'],
  ['视频合成', 'Video synthesis'],
  ['片段', 'segment'],
  ['正在处理第 ', 'Processing segment '],
  [' 个片段，共 ', ' of '],
  [' 个片段', ' segments'],
];

export const translateTaskText = (text?: string | null): string => {
  if (!text) return '';

  return replacements.reduce((current, [from, to]) => {
    return current.split(from).join(to);
  }, text);
};
