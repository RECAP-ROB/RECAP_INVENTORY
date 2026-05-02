import { createContext, useContext, useState, ReactNode } from 'react';

export type RobotArmStatus = 'READY' | 'BUSY' | 'ERROR' | 'IDLE';
export type RobotChassisStatus = 'IDLE' | 'MOVING' | 'ERROR';

interface RobotStatusState {
  robotArmStatus: RobotArmStatus;
  robotChassisStatus: RobotChassisStatus;
  robotStep: string;
  robotProgress: number;
  setRobotArmStatus: (value: RobotArmStatus) => void;
  setRobotChassisStatus: (value: RobotChassisStatus) => void;
  setRobotStep: (value: string) => void;
  setRobotProgress: (value: number) => void;
}

const RobotStatusContext = createContext<RobotStatusState | undefined>(undefined);

export const RobotStatusProvider = ({ children }: { children: ReactNode }) => {
  const [robotArmStatus, setRobotArmStatus] = useState<RobotArmStatus>('IDLE');
  const [robotChassisStatus, setRobotChassisStatus] = useState<RobotChassisStatus>('IDLE');
  const [robotStep, setRobotStep] = useState<string>('Idle');
  const [robotProgress, setRobotProgress] = useState<number>(0);

  return (
    <RobotStatusContext.Provider value={{
      robotArmStatus,
      robotChassisStatus,
      robotStep,
      robotProgress,
      setRobotArmStatus,
      setRobotChassisStatus,
      setRobotStep,
      setRobotProgress,
    }}>
      {children}
    </RobotStatusContext.Provider>
  );
};

export const useRobotStatus = () => {
  const context = useContext(RobotStatusContext);
  if (!context) {
    throw new Error('useRobotStatus must be used within RobotStatusProvider');
  }
  return context;
};
