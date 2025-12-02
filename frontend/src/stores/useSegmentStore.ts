import { create } from 'zustand';
import { Segment } from '../types/segment';

interface SegmentStore {
  segments: Segment[];
  currentSegmentId: number | null;
  setSegments: (segments: Segment[]) => void;
  updateSegment: (segment: Segment) => void;
  deleteSegment: (segmentId: number) => void;
  setCurrentSegment: (segmentId: number | null) => void;
}

export const useSegmentStore = create<SegmentStore>((set) => ({
  segments: [],
  currentSegmentId: null,
  setSegments: (segments) => set({ segments }),
  updateSegment: (segment) =>
    set((state) => ({
      segments: state.segments.map((s) =>
        s.id === segment.id ? segment : s
      ),
    })),
  deleteSegment: (segmentId) =>
    set((state) => ({
      segments: state.segments.filter((s) => s.id !== segmentId),
    })),
  setCurrentSegment: (segmentId) => set({ currentSegmentId: segmentId }),
}));


