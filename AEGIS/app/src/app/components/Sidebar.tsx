import { LayoutDashboard, FileText, Building2, Upload, ImageIcon, VideoIcon } from 'lucide-react';
import { useState, useRef } from 'react';
import { motion } from 'motion/react';

interface SidebarProps {
  activeView: string;
  setActiveView: (view: string) => void;
}

export default function Sidebar({ activeView, setActiveView }: SidebarProps) {
  const [dragActive, setDragActive] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; type: string }[]>([]);
  const jpgInputRef = useRef<HTMLInputElement>(null);
  const mp4InputRef = useRef<HTMLInputElement>(null);

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'reports', label: 'Reports', icon: FileText },
    { id: 'bbmp', label: 'BBMP', icon: Building2 },
  ];

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent, fileType: 'jpg' | 'mp4') => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      const isValidType =
        (fileType === 'jpg' && file.type.startsWith('image/')) ||
        (fileType === 'mp4' && file.type.startsWith('video/'));

      if (isValidType) {
        setUploadedFiles((prev) => [...prev, { name: file.name, type: fileType }]);
        alert(`File "${file.name}" uploaded successfully!`);
      } else {
        alert(`Please upload a valid ${fileType.toUpperCase()} file`);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>, fileType: 'jpg' | 'mp4') => {
    const files = e.currentTarget.files;
    if (files && files.length > 0) {
      const file = files[0];
      setUploadedFiles((prev) => [...prev, { name: file.name, type: fileType }]);
      alert(`File "${file.name}" uploaded successfully!`);
    }
  };

  return (
    <div className="w-64 bg-black/40 backdrop-blur-xl border-r border-cyan-500/20 p-6 flex flex-col gap-6">
      <div className="space-y-2 mt-16">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;

          return (
            <button
              key={item.id}
              onClick={() => setActiveView(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-300 ${
                isActive
                  ? 'bg-cyan-500/20 border border-cyan-400/50 shadow-[0_0_10px_rgba(34,211,238,0.3)]'
                  : 'hover:bg-white/5 border border-transparent'
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? 'text-cyan-400' : 'text-gray-400'}`} />
              <span className={`font-medium ${isActive ? 'text-cyan-400' : 'text-gray-300'}`}>
                {item.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-8">
        <div className="flex items-center gap-2 mb-4 px-4">
          <Upload className="w-5 h-5 text-emerald-400" />
          <span className="font-medium text-emerald-400">Upload</span>
        </div>

        <div className="space-y-3">
          {/* JPG Upload */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={(e) => handleDrop(e, 'jpg')}
            className={`w-full px-4 py-3 rounded-lg border transition-all duration-300 flex items-center gap-2 justify-center cursor-pointer ${
              dragActive
                ? 'bg-cyan-500/30 border-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.5)]'
                : 'bg-cyan-500/10 border-cyan-400/50 hover:shadow-[0_0_10px_rgba(34,211,238,0.3)]'
            }`}
            onClick={() => jpgInputRef.current?.click()}
          >
            <ImageIcon className="w-4 h-4 text-cyan-400" />
            <span className="text-cyan-400 font-medium">Upload JPG</span>
            <input
              ref={jpgInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.gif,.webp"
              onChange={(e) => handleFileSelect(e, 'jpg')}
              className="hidden"
            />
          </div>

          {/* MP4 Upload */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={(e) => handleDrop(e, 'mp4')}
            className={`w-full px-4 py-3 rounded-lg border transition-all duration-300 flex items-center gap-2 justify-center cursor-pointer ${
              dragActive
                ? 'bg-cyan-500/30 border-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.5)]'
                : 'bg-cyan-500/10 border-cyan-400/50 hover:shadow-[0_0_10px_rgba(34,211,238,0.3)]'
            }`}
            onClick={() => mp4InputRef.current?.click()}
          >
            <VideoIcon className="w-4 h-4 text-cyan-400" />
            <span className="text-cyan-400 font-medium">Upload MP4</span>
            <input
              ref={mp4InputRef}
              type="file"
              accept=".mp4,.avi,.mov,.webm,.flv"
              onChange={(e) => handleFileSelect(e, 'mp4')}
              className="hidden"
            />
          </div>
        </div>

        {/* Uploaded Files List */}
        {uploadedFiles.length > 0 && (
          <div className="mt-6 pt-4 border-t border-cyan-500/20">
            <h3 className="text-xs font-bold text-cyan-400 mb-3 uppercase">Uploaded Files</h3>
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {uploadedFiles.map((file, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-xs p-2 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 truncate"
                  title={file.name}
                >
                  {file.type === 'jpg' ? '🖼️' : '🎬'} {file.name}
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
