import { useCallback, useRef, useState } from "react";
import { apiUploadBinary } from "@/services/api-client";
import { buildTar, type TarEntry } from "@/utils/tar-builder";

interface Props {
  onSuccess: (result: { id: string; name: string; file_count: number }) => void;
  onError: (error: string) => void;
  onCancel: () => void;
}

interface FileEntry {
  path: string;
  file: File;
}

/**
 * Recursively read files from a DataTransferItemList using the File System API.
 * Uses webkitGetAsEntry() — supported in Chrome, Edge, and Opera.
 * Falls back to reading directly from item.getAsFile() for flat file drops.
 */
async function readFilesFromDataTransfer(
  items: DataTransferItemList,
): Promise<FileEntry[]> {
  const result: FileEntry[] = [];

  async function traverse(entry: FileSystemEntry, parentPath: string) {
    if (entry.isFile) {
      const fileEntry = entry as FileSystemFileEntry;
      const file = await new Promise<File>((resolve, reject) => {
        fileEntry.file(resolve, reject);
      });
      const relPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
      result.push({ path: relPath, file });
    } else if (entry.isDirectory) {
      const dirEntry = entry as FileSystemDirectoryEntry;
      const reader = dirEntry.createReader();
      const relPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;

      // readAllEntries: directory reader may return results in batches
      const allEntries: FileSystemEntry[] = [];
      let batch: FileSystemEntry[];
      do {
        batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
          reader.readEntries(resolve, reject);
        });
        allEntries.push(...batch);
      } while (batch.length > 0);

      for (const child of allEntries) {
        await traverse(child, relPath);
      }
    }
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const entry = item.webkitGetAsEntry?.();
    if (entry) {
      await traverse(entry, "");
    }
  }

  return result;
}

/**
 * Read files from a file input with webkitdirectory attribute.
 * Firefox does not support webkitGetAsEntry but supports webkitdirectory.
 */
async function readFilesFromInput(files: FileList): Promise<FileEntry[]> {
  const result: FileEntry[] = [];
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    // webkitRelativePath gives the relative path within the selected folder
    const path = file.webkitRelativePath || file.name;
    result.push({ path, file });
  }
  return result;
}

async function entriesToTar(entries: FileEntry[]): Promise<Uint8Array> {
  const tarEntries: TarEntry[] = await Promise.all(
    entries.map(async (entry) => ({
      path: entry.path,
      data: new Uint8Array(await entry.file.arrayBuffer()),
    })),
  );
  return buildTar(tarEntries);
}

export default function FolderUploader({ onSuccess, onError, onCancel }: Props) {
  const [status, setStatus] = useState<"idle" | "reading" | "packing" | "uploading">("idle");
  const [progress, setProgress] = useState({ files: 0, bytes: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const processUpload = useCallback(
    async (entries: FileEntry[]) => {
      try {
        setStatus("packing");
        const tarBytes = await entriesToTar(entries);
        setProgress({ files: entries.length, bytes: tarBytes.length });

        setStatus("uploading");
        const result = await apiUploadBinary<{
          id: string;
          name: string;
          file_count: number;
          message: string;
        }>("/skills/upload-directory", tarBytes, "application/x-tar");

        onSuccess(result);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Upload failed";
        onError(msg);
      }
    },
    [onSuccess, onError],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (!e.dataTransfer?.items) return;

      setStatus("reading");
      try {
        const entries = await readFilesFromDataTransfer(e.dataTransfer.items);
        if (entries.length === 0) {
          onError("No files found in dropped folder");
          return;
        }
        await processUpload(entries);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Failed to read folder";
        onError(msg);
      }
    },
    [processUpload, onError],
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      setStatus("reading");
      try {
        const entries = await readFilesFromInput(files);
        if (entries.length === 0) {
          onError("No files found in selected folder");
          return;
        }
        await processUpload(entries);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Failed to read folder";
        onError(msg);
      }
    },
    [processUpload, onError],
  );

  const busy = status !== "idle";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
        <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">
          Upload Skill Folder
        </h3>

        {/* Drop zone */}
        <div
          ref={dropRef}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={[
            "border-2 border-dashed rounded-lg p-8 text-center transition-colors",
            dragOver
              ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
              : "border-gray-300 dark:border-gray-600",
            busy ? "pointer-events-none opacity-50" : "cursor-pointer",
          ].join(" ")}
          onClick={() => !busy && fileInputRef.current?.click()}
        >
          {busy ? (
            <div className="space-y-2">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                {status === "reading" && "Reading folder contents..."}
                {status === "packing" && `Packing ${progress.files} files into tar archive...`}
                {status === "uploading" &&
                  `Uploading ${progress.files} files (${(progress.bytes / 1024).toFixed(1)} KB)...`}
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                <div
                  className={[
                    "h-full rounded-full transition-all duration-300",
                    status === "reading" && "bg-yellow-500 w-1/3",
                    status === "packing" && "bg-blue-500 w-2/3",
                    status === "uploading" && "bg-green-500 animate-pulse w-5/6",
                  ].join(" ")}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-4xl">📁</div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Drag & drop a skill folder here, or click to select
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Folder must contain a SKILL.md file
              </p>
            </div>
          )}
        </div>

        {/* Hidden file input for folder selection */}
        <input
          ref={fileInputRef}
          type="file"
          // @ts-expect-error webkitdirectory is widely supported but not in React types
          webkitdirectory=""
          multiple
          className="hidden"
          onChange={handleFileSelect}
        />

        {/* Actions */}
        <div className="mt-4 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}