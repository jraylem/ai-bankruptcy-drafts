export interface PleadingServiceFlags {
  withOrderSustaining: boolean;
  withService: boolean;
}

export const getPleadingServiceFlags = (motionType: string): PleadingServiceFlags => {
  if (motionType === 'claim') {
    return { withOrderSustaining: false, withService: true };
  }

  if (
    motionType === 'objection-sustain' ||
    motionType === 'certificate-of-service' ||
    motionType === 'service' ||
    motionType === 'ex-parte-extension' ||
    motionType.startsWith('order-')
  ) {
    return { withOrderSustaining: false, withService: false };
  }

  return { withOrderSustaining: false, withService: true };
};
